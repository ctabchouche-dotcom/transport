# -*- coding: utf-8 -*-
import re
from datetime import timedelta

import pytz

from odoo import fields
from odoo.tests.common import HttpCase, tagged

from odoo.addons.transport.controllers.booking import WEEKDAYS


def _public_local(env, value):
    tzname = env.company.partner_id.tz or 'Africa/Algiers'
    return pytz.UTC.localize(value).astimezone(pytz.timezone(tzname))


@tagged('post_install', '-at_install')
class TestTransportBookingPage(HttpCase):

    def _open(self, url, data=None):
        if not getattr(self, 'session', None):
            self.authenticate(None, None)
        return self.url_open(url, data=data)

    def test_public_page_holds_a_seat_until_the_counter_confirms(self):
        origin = self.env['transport.stop'].create({'name': 'Alger page', 'code': 'P-ALG'})
        destination = self.env['transport.stop'].create({'name': 'Oran page', 'code': 'P-ORN'})
        hidden = self.env['transport.line'].create({
            'name': 'Navette cachée',
            'code': 'P-B2B',
            'line_type': 'b2b',
            'seat_capacity': 10,
            'b2b_seat_reserve': 10,
            'stop_ids': [
                (0, 0, {'stop_id': origin.id, 'sequence': 10}),
                (0, 0, {'stop_id': destination.id, 'sequence': 20}),
            ],
        })
        line = self.env['transport.line'].create({
            'name': 'Alger Oran page',
            'code': 'P-PUB',
            'line_type': 'b2c',
            'seat_capacity': 10,
            'b2b_seat_reserve': 0,
            'fare': 1500,
            'cancel_hours': 24,
            'refund_percent': 100,
            'stop_ids': [
                (0, 0, {'stop_id': origin.id, 'sequence': 10}),
                (0, 0, {'stop_id': destination.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': origin.id,
            'destination_stop_id': destination.id,
            'price': 1500,
        })
        start = fields.Datetime.now() + timedelta(days=3)
        self.env['transport.departure'].create({
            'line_id': hidden.id,
            'departure_datetime': start,
        })
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': start + timedelta(hours=2),
        })
        closed = self._open('/reserver-un-billet')
        self.assertEqual(closed.status_code, 200)
        self.assertIn(line.name, closed.text)
        self.assertNotIn(hidden.name, closed.text)

        local = _public_local(self.env, departure.departure_datetime)
        day = local.strftime('%Y-%m-%d')
        chosen = self._open('/reserver-un-billet?line_id=%s&day=%s' % (line.id, day))
        self.assertIn('%s %s' % (WEEKDAYS[local.weekday()], local.strftime('%d/%m')), chosen.text)
        self.assertIn('value="%s"' % departure.id, chosen.text)
        token = re.search(r'name="csrf_token" value="([^"]+)"', chosen.text)
        self.assertTrue(token)
        sent = self._open('/reserver-un-billet/envoyer', data={
            'csrf_token': token.group(1),
            'departure_id': str(departure.id),
            'origin_stop_id': str(origin.id),
            'destination_stop_id': str(destination.id),
            'passenger_name': 'Lina Hadj',
            'phone': '0555121212',
            'email': 'lina.page@example.dz',
            'seat_count': '1',
        })
        self.assertEqual(sent.status_code, 200)
        self.assertIn('/reserver-un-billet/paiement/', sent.url)
        booking = self.env['transport.booking'].search([
            ('departure_id', '=', departure.id),
            ('passenger_name', '=', 'Lina Hadj'),
        ])
        self.assertEqual(booking.state, 'held')
        self.assertEqual(booking.amount_total, 1500)
        self.assertEqual(booking.seat_label, '1')
        self.assertIn('Siège(s)', sent.text)
        self.assertIn('1 500 DZD', sent.text)
        pay_token = re.search(r'name="csrf_token" value="([^"]+)"', sent.text)
        self.assertTrue(pay_token)
        paid = self._open(sent.url, data={'csrf_token': pay_token.group(1)})
        self.assertEqual(paid.status_code, 200)
        self.assertIn('attachment', paid.headers.get('Content-Disposition', ''))
        self.assertTrue(paid.content.startswith(b'%PDF-') or b'Lina Hadj' in paid.content)
        booking.invalidate_recordset()
        self.assertEqual(booking.state, 'confirmed')
        self.assertTrue(booking.paid)
        self.assertTrue(booking.ticket_id)
        again = self._open(sent.url)
        self.assertIn('Annuler la réservation', again.text)
        cancel_token = re.search(r'name="csrf_token" value="([^"]+)"', again.text)
        self.assertTrue(cancel_token)
        cancelled = self._open(
            '/reserver-un-billet/annuler/%s/%s' % (booking.id, booking.access_token()),
            data={'csrf_token': cancel_token.group(1)},
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertIn('annulée', cancelled.text)
        booking.invalidate_recordset()
        self.assertEqual(booking.state, 'cancelled')
        self.assertEqual(booking.refund_amount, 1500)
        self.assertEqual(booking.ticket_id.state, 'cancelled')

    def test_camera_page_boards_the_ticket(self):
        origin = self.env['transport.stop'].create({'name': 'Alger scan', 'code': 'C-ALG'})
        destination = self.env['transport.stop'].create({'name': 'Oran scan', 'code': 'C-ORN'})
        line = self.env['transport.line'].create({
            'name': 'Scan page',
            'code': 'C-PUB',
            'line_type': 'b2c',
            'seat_capacity': 10,
            'stop_ids': [
                (0, 0, {'stop_id': origin.id, 'sequence': 10}),
                (0, 0, {'stop_id': destination.id, 'sequence': 20}),
            ],
        })
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=5),
            'release_hours': 0,
        })
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Irisbus scan'})
        model = self.env['fleet.vehicle.model'].create({'name': 'Scan', 'brand_id': brand.id})
        vehicle = self.env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': 'SCAN-1'})
        vehicle.seats = 20
        driver = self.env['hr.employee'].create({'name': 'Chauffeur scan'})
        expires = departure._service_date() + timedelta(days=30)
        for doc_type in ('license', 'medical', 'training'):
            self.env['transport.driver.document'].create({
                'employee_id': driver.id,
                'doc_type': doc_type,
                'expires_on': expires,
            })
        departure.write({'vehicle_id': vehicle.id, 'driver_id': driver.id})
        departure.action_assign()
        departure.action_open_boarding()
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': origin.id,
            'destination_stop_id': destination.id,
            'price': 500,
        })
        booking = departure.book(origin, destination, 1, 'Nora Saidi')
        booking.pay_counter('cash')
        self.authenticate('admin', 'admin')
        page = self.url_open(departure.scan_path())
        self.assertEqual(page.status_code, 200)
        self.assertIn('scan-video', page.text)
        self.assertIn('jsQR.js', page.text)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        self.assertTrue(token)
        boarded = self.url_open(departure.scan_path(), data={
            'csrf_token': token.group(1),
            'payload': booking.ticket_id.qr_payload,
        })
        self.assertEqual(boarded.status_code, 200)
        self.assertIn('Nora Saidi est à bord.', boarded.text)
        booking.invalidate_recordset()
        self.assertEqual(booking.state, 'boarded')

    def test_fixed_reader_and_tracker_use_the_bus_token(self):
        origin = self.env['transport.stop'].create({'name': 'Alger boitier', 'code': 'D-ALG'})
        destination = self.env['transport.stop'].create({'name': 'Oran boitier', 'code': 'D-ORN'})
        line = self.env['transport.line'].create({
            'name': 'Boitier',
            'code': 'D-PUB',
            'line_type': 'b2c',
            'seat_capacity': 10,
            'stop_ids': [
                (0, 0, {'stop_id': origin.id, 'sequence': 10}),
                (0, 0, {'stop_id': destination.id, 'sequence': 20}),
            ],
        })
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Irisbus device'})
        model = self.env['fleet.vehicle.model'].create({'name': 'Device', 'brand_id': brand.id})
        vehicle = self.env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': 'DEV-1'})
        vehicle.seats = 20
        self.assertEqual(len(vehicle.transport_device_token), 32)
        other = self.env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': 'DEV-2'})
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=4),
            'release_hours': 0,
        })
        driver = self.env['hr.employee'].create({'name': 'Chauffeur boitier'})
        expires = departure._service_date() + timedelta(days=30)
        for doc_type in ('license', 'medical', 'training'):
            self.env['transport.driver.document'].create({
                'employee_id': driver.id,
                'doc_type': doc_type,
                'expires_on': expires,
            })
        departure.write({'vehicle_id': vehicle.id, 'driver_id': driver.id})
        departure.action_assign()
        departure.action_open_boarding()
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': origin.id,
            'destination_stop_id': destination.id,
            'price': 500,
        })
        booking = departure.book(origin, destination, 1, 'Yasmine Boudiaf')
        booking.pay_counter('cash')
        self.authenticate(None, None)
        idle = self.url_open('/bus/%s/position?lat=36.7&lon=3.0' % other.transport_device_token)
        self.assertEqual(idle.status_code, 200)
        other.invalidate_recordset()
        self.assertEqual(other.last_latitude, 36.7)
        refused = self.url_open(
            '/bus/%s/scan?payload=%s' % (other.transport_device_token, booking.ticket_id.qr_payload),
        )
        self.assertEqual(refused.status_code, 409)
        self.assertIn("n'a pas de départ", refused.text)
        point = self.url_open(
            '/bus/%s/position?lat=36.7538&lon=3.0588' % vehicle.transport_device_token,
        )
        self.assertEqual(point.status_code, 200)
        self.assertEqual(point.text, 'ok')
        departure.invalidate_recordset()
        self.assertEqual(departure.last_latitude, 36.7538)
        self.assertEqual(departure.last_longitude, 3.0588)
        unknown = self.url_open('/bus/%s/scan?payload=%s' % ('a' * 32, booking.ticket_id.qr_payload))
        self.assertEqual(unknown.status_code, 404)
        boarded = self.url_open(
            '/bus/%s/scan' % vehicle.transport_device_token,
            data={'code': booking.ticket_id.qr_payload},
        )
        self.assertEqual(boarded.status_code, 200)
        self.assertEqual(boarded.text, 'Yasmine Boudiaf')
        booking.invalidate_recordset()
        self.assertEqual(booking.state, 'boarded')
