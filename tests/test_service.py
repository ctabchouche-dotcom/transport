# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.transport.models.seatmap import iter_plan_seats


@tagged('post_install', '-at_install')
class TestTransportService(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = 'UTC'
        cls.casa = cls.env['transport.stop'].create({'name': 'Alger test', 'code': 'S-ALG'})
        cls.rabat = cls.env['transport.stop'].create({'name': 'Oran test', 'code': 'S-ORN'})
        cls.line = cls.env['transport.line'].create({
            'name': 'Service',
            'code': 'SRV',
            'seat_capacity': 4,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'stop_ids': [
                (0, 0, {'stop_id': cls.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': cls.rabat.id, 'sequence': 20}),
            ],
        })

    def make_departure(self):
        return self.env['transport.departure'].create({
            'line_id': self.line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=5),
            'release_hours': 0,
        })

    def test_trip_price_and_timed_refund(self):
        mid = self.env['transport.stop'].create({'name': 'Blida test', 'code': 'S-BLI'})
        line = self.env['transport.line'].create({
            'name': 'Tarif',
            'code': 'TARIF',
            'seat_capacity': 4,
            'cancel_hours': 2,
            'refund_percent': 50,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': mid.id, 'sequence': 20}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 30}),
            ],
        })
        self.env['transport.fare'].create([
            {
                'line_id': line.id,
                'origin_stop_id': self.casa.id,
                'destination_stop_id': mid.id,
                'price': 400,
            },
            {
                'line_id': line.id,
                'origin_stop_id': self.casa.id,
                'destination_stop_id': self.rabat.id,
                'price': 700,
            },
        ])
        later = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=5),
        })
        soon = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=1),
        })
        booking = self.env['transport.booking'].book_public(
            later.id, self.casa.id, mid.id, 'Nora Saidi', '0555000111', seat_count=2,
        )
        self.assertEqual(booking.fare_unit, 400)
        self.assertEqual(booking.amount_total, 800)
        self.assertEqual(booking.seat_label, '1, 2')
        with self.assertRaises(UserError):
            later.book(self.casa, mid, 1, 'Karim', seat_numbers=[1])
        again = later.book(mid, self.rabat, 1, 'Karim', seat_numbers=[1])
        self.assertEqual(again.seat_label, '1')
        booking.pay_online()
        booking.with_context(transport_passenger_cancel=True).action_cancel()
        self.assertEqual(booking.state, 'cancelled')
        self.assertEqual(booking.refund_amount, 400)
        self.assertEqual(booking.ticket_id.state, 'cancelled')
        freed = later.book(self.casa, mid, 1, 'Yanis')
        self.assertEqual(freed.state, 'held')

        late = self.env['transport.booking'].book_public(
            soon.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111', seat_count=1,
        )
        self.assertEqual(late.amount_total, 700)
        late.pay_online()
        with self.assertRaises(UserError):
            late.with_context(transport_passenger_cancel=True).action_cancel()
        self.assertEqual(late.state, 'confirmed')
        late.action_cancel()
        self.assertEqual(late.state, 'cancelled')
        self.assertEqual(late.refund_amount, 0)

    def test_counter_cash_and_card_use_the_same_receipt(self):
        line = self.env['transport.line'].create({
            'name': 'Guichet',
            'code': 'GUICHET',
            'seat_capacity': 4,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 900,
        })
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=5),
            'release_hours': 0,
        })
        cash = self.env['transport.booking'].book_public(
            departure.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111',
        )
        ticket = cash.pay_counter('cash')
        self.assertEqual(cash.state, 'confirmed')
        self.assertTrue(cash.paid)
        self.assertEqual(cash.payment_method, 'cash')
        self.assertEqual(cash.payment_reference, 'ESP-%s' % cash.id)
        self.assertEqual(cash.amount_total, 900)
        self.assertEqual(ticket, cash.ticket_id)
        action = cash.action_print_receipt()
        self.assertEqual(action['report_name'], 'transport.report_receipt')
        with self.assertRaises(UserError):
            cash.pay_counter('tpe')

        card = departure.book(self.casa, self.rabat, 2, 'Samir Kaci')
        self.assertFalse(card.amount_total)
        card.pay_counter('tpe')
        self.assertEqual(card.payment_method, 'tpe')
        self.assertEqual(card.payment_reference, 'TPE-%s' % card.id)
        self.assertEqual(card.amount_total, 1800)
        self.assertEqual(card.fare_unit, 900)

    def test_departure_result_keeps_sales_refunds_and_fill(self):
        line = self.env['transport.line'].create({
            'name': 'Résultat',
            'code': 'RESULT',
            'seat_capacity': 4,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'cancel_hours': 24,
            'refund_percent': 50,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 1000,
        })
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=48),
            'release_hours': 0,
        })
        kept = self.env['transport.booking'].book_public(
            departure.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111', seat_count=2,
        )
        kept.pay_counter('cash')
        returned = departure.book(self.casa, self.rabat, 1, 'Samir Kaci')
        returned.pay_counter('tpe')
        returned.action_cancel()
        self.assertEqual(departure.seats_sold, 2)
        self.assertEqual(departure.amount_collected, 3000)
        self.assertEqual(departure.amount_refunded, 500)
        self.assertEqual(departure.amount_net, 2500)
        leg = departure.leg_ids
        self.assertEqual(leg.seats_taken, 2)
        self.assertEqual(leg.fill_percent, 50)

    def test_confirm_issues_a_signed_ticket_and_scan_boards(self):
        departure = self.make_departure()
        partner = self.env['res.partner'].create({
            'name': 'Amina Benali',
            'email': 'amina.ticket@example.com',
        })
        booking = departure.book(self.casa, self.rabat, 1, 'Amina Benali', partner=partner)
        self.env['transport.fare'].create({
            'line_id': self.line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 500,
        })
        booking.action_confirm()
        with self.assertRaises(UserError):
            booking.action_board()
        booking.pay_counter('cash')
        ticket = booking.ticket_id
        self.assertTrue(ticket)
        self.assertTrue(ticket._signature_matches())
        self.assertTrue(ticket.qr_src().startswith('data:image/png;base64,'))
        self.assertTrue(self.env['mail.mail'].search_count([
            ('model', '=', 'transport.ticket'),
            ('res_id', '=', ticket.id),
        ]))
        with self.assertRaises(UserError):
            self.env['transport.ticket'].board_payload(ticket.qr_payload, departure)
        self._open_boarding(departure)
        with self.assertRaises(UserError):
            self.env['transport.ticket'].board_payload('TRP:0:forged', departure)
        self.env['transport.ticket'].board_payload(ticket.qr_payload, departure)
        self.assertEqual(booking.state, 'boarded')
        self.assertEqual(ticket.state, 'boarded')
        with self.assertRaises(UserError):
            booking.action_cancel()

    def test_noshow_frees_the_seat(self):
        departure = self.make_departure()
        departure.seat_capacity = 1
        booking = departure.book(self.casa, self.rabat, 1, 'Sara')
        booking.action_confirm()
        self._open_boarding(departure)
        booking.action_noshow()
        self.assertEqual(booking.ticket_id.state, 'noshow')
        replacement = departure.book(self.casa, self.rabat, 1, 'Omar')
        self.assertEqual(replacement.state, 'held')

    def test_critical_check_blocks_departure(self):
        departure = self.make_departure()
        self._open_boarding(departure)
        brakes = departure.check_ids.filtered(lambda check: 'freinage' in check.name)
        brakes.result = 'ko'
        departure.check_ids.filtered(lambda check: check != brakes).write({'result': 'ok'})
        with self.assertRaises(UserError):
            departure.action_start()
        brakes.result = 'ok'
        departure.action_start()
        self.assertEqual(departure.state, 'in_progress')

    def test_contract_quota_limits_subscribers(self):
        company = self.env['res.partner'].create({'name': 'Atlas', 'is_company': True})
        contract = self.env['transport.contract'].create({
            'partner_id': company.id,
            'line_ids': [(6, 0, self.line.ids)],
            'date_start': fields.Date.context_today(self.line) - timedelta(days=1),
            'seat_quota': 1,
        })
        contract.action_open()
        subscriber = self.env['transport.subscriber'].create({
            'name': 'Karim',
            'contract_id': contract.id,
        })
        other = self.env['transport.subscriber'].create({
            'name': 'Nadia',
            'contract_id': contract.id,
        })
        departure = self.make_departure()
        departure.book(self.casa, self.rabat, 1, '', subscriber=subscriber)
        with self.assertRaises(UserError):
            departure.book(self.casa, self.rabat, 1, '', subscriber=other)
        contract.action_close()
        with self.assertRaises(UserError):
            departure.book(self.casa, self.rabat, 1, 'Nadia', subscriber=other)

    def _vehicle(self, seats, plate):
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Irisbus %s' % plate})
        model = self.env['fleet.vehicle.model'].create({
            'name': 'Crossway %s' % plate,
            'brand_id': brand.id,
        })
        vehicle = self.env['fleet.vehicle'].create({
            'model_id': model.id,
            'license_plate': plate,
        })
        vehicle.seats = seats
        return vehicle

    def test_delay_swap_and_rebook(self):
        first = self.make_departure()
        second = self.env['transport.departure'].create({
            'line_id': self.line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=8),
            'release_hours': 0,
        })
        booking = first.book(self.casa, self.rabat, 1, 'Nora Saidi')
        booking.action_confirm()
        ticket = booking.ticket_id
        first.set_delay(20, 'Circulation')
        self.assertEqual(first.delay_minutes, 20)
        self.assertEqual(
            first.effective_datetime,
            first.departure_datetime + timedelta(minutes=20),
        )
        first.set_delay(0, 'repris')
        self.assertFalse(first.delay_reason)
        bus = self._vehicle(4, 'BUS-4')
        small = self._vehicle(0, 'BUS-0')
        first.write({'vehicle_id': bus.id, 'state': 'assigned'})
        with self.assertRaises(UserError):
            first.swap_vehicle(small)
        tight = self._vehicle(1, 'BUS-1')
        other = first.book(self.casa, self.rabat, 1, 'Samir Kaci')
        with self.assertRaises(UserError):
            first.swap_vehicle(tight)
        other.action_cancel()
        first.swap_vehicle(tight)
        self.assertEqual(first.vehicle_id, tight)
        self.assertEqual(first.seat_capacity, 1)
        full = second.book(self.casa, self.rabat, 1, 'Ines Kaci')
        second.seat_capacity = 1
        with self.assertRaises(UserError):
            booking.action_rebook(second)
        full.action_cancel()
        booking.action_rebook(second)
        self.assertEqual(booking.departure_id, second)
        self.assertEqual(booking.ticket_id, ticket)
        self.assertEqual(booking.state, 'confirmed')
        self.assertTrue(booking.seat_label)
        again = first.book(self.casa, self.rabat, 1, 'Yacine Meziane')
        self.assertEqual(again.departure_id, first)

    def test_delay_and_rebook_email_the_passenger(self):
        line = self.env['transport.line'].create({
            'name': 'Courrier',
            'code': 'MAIL',
            'seat_capacity': 4,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 500,
        })
        first = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=6),
            'release_hours': 0,
        })
        second = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=10),
            'release_hours': 0,
        })
        told = self.env['transport.booking'].book_public(
            first.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111',
            email='nora.mail@example.dz',
        )
        told.action_confirm()
        silent = first.book(self.casa, self.rabat, 1, 'Sans Adresse')
        silent.action_confirm()
        Mail = self.env['mail.mail']
        before = Mail.search_count([('email_to', '=', 'nora.mail@example.dz')])
        first.set_delay(25, 'Circulation')
        delay_mails = Mail.search([
            ('email_to', '=', 'nora.mail@example.dz'),
            ('subject', 'ilike', 'Retard'),
        ])
        self.assertEqual(len(delay_mails), 1)
        self.assertFalse(Mail.search_count([('email_to', '=', False), ('model', '=', 'transport.booking'), ('res_id', '=', silent.id)]))
        first.set_delay(0)
        self.assertTrue(Mail.search_count([
            ('email_to', '=', 'nora.mail@example.dz'),
            ('subject', 'ilike', 'Horaire rétabli'),
        ]))
        told.action_rebook(second)
        self.assertTrue(Mail.search_count([
            ('email_to', '=', 'nora.mail@example.dz'),
            ('subject', 'ilike', 'Billet reporté'),
        ]))
        self.assertGreater(Mail.search_count([('email_to', '=', 'nora.mail@example.dz')]), before)

    def test_reference_and_phone_open_the_ticket(self):
        line = self.env['transport.line'].create({
            'name': 'Retrouver',
            'code': 'FIND',
            'seat_capacity': 4,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 500,
        })
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=6),
            'release_hours': 0,
        })
        booking = self.env['transport.booking'].book_public(
            departure.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555 12 12 12',
        )
        Booking = self.env['transport.booking']
        self.assertEqual(booking.phone, '0555 12 12 12')
        found = Booking.find_public(booking.name.lower(), '+213555121212')
        self.assertEqual(found, booking)
        with self.assertRaises(UserError):
            Booking.find_public(booking.name, '0555000000')
        with self.assertRaises(UserError):
            Booking.find_public('INCONNU', '0555121212')

    def test_stop_times_follow_distance_and_delay(self):
        mid = self.env['transport.stop'].create({'name': 'Blida heure', 'code': 'H-BLI'})
        line = self.env['transport.line'].create({
            'name': 'Horaires',
            'code': 'HEURE',
            'seat_capacity': 4,
            'average_speed': 60,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10, 'distance_km': 0}),
                (0, 0, {'stop_id': mid.id, 'sequence': 20, 'distance_km': 60}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 30, 'distance_km': 30}),
            ],
        })
        start = fields.Datetime.from_string('2026-11-10 08:00:00')
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': start,
            'release_hours': 0,
        })
        self.assertEqual(departure.stop_passage(self.casa), start)
        self.assertEqual(departure.stop_passage(mid), start + timedelta(hours=1))
        self.assertEqual(departure.stop_passage(self.rabat), start + timedelta(hours=1, minutes=30))
        departure.set_delay(20, 'Circulation')
        self.assertEqual(departure.stop_passage(self.casa), start + timedelta(minutes=20))
        self.assertEqual(departure.stop_passage(self.rabat), start + timedelta(hours=1, minutes=50))
        self.assertEqual([row['name'] for row in departure.passage_rows()], [
            'Alger test', 'Blida heure', 'Oran test',
        ])

    def test_each_seat_carries_its_passenger(self):
        line = self.env['transport.line'].create({
            'name': 'Noms',
            'code': 'NOMS',
            'seat_capacity': 4,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 400,
        })
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=6),
            'release_hours': 0,
        })
        booking = self.env['transport.booking'].book_public(
            departure.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111',
            seat_count=3, seat_names=['Samir Kaci'],
        )
        names = booking.seat_ids.sorted('number').mapped('passenger_name')
        self.assertEqual(names, ['Nora Saidi', 'Samir Kaci', 'Passager 3'])
        self.assertIn('Samir Kaci', booking.seat_detail)
        booking.action_confirm()
        rows = departure.manifest_rows()
        self.assertEqual([row['name'] for row in rows], names)
        self.assertEqual([row['seat'] for row in rows], [1, 2, 3])

    def test_waitlist_offers_the_freed_seat_in_order(self):
        line = self.env['transport.line'].create({
            'name': 'Attente',
            'code': 'ATTENTE',
            'seat_capacity': 1,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 300,
        })
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=6),
            'release_hours': 0,
        })
        Wait = self.env['transport.waitlist']
        with self.assertRaises(UserError):
            Wait.join_public(
                departure.id, self.casa.id, self.rabat.id, 'Trop tôt', '0555111000', seat_count=1,
            )
        taken = self.env['transport.booking'].book_public(
            departure.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111',
        )
        taken.action_confirm()
        first = Wait.join_public(
            departure.id, self.casa.id, self.rabat.id, 'Samir Kaci', '0555222000',
            email='samir.wait@example.dz',
        )
        second = Wait.join_public(
            departure.id, self.casa.id, self.rabat.id, 'Ines Kaci', '0555333000',
        )
        self.assertEqual(first.state, 'waiting')
        taken.action_cancel()
        self.assertEqual(first.state, 'offered')
        self.assertEqual(second.state, 'waiting')
        self.assertTrue(self.env['mail.mail'].search_count([
            ('email_to', '=', 'samir.wait@example.dz'),
            ('subject', 'ilike', 'libérée'),
        ]))
        booking = first.claim()
        self.assertEqual(first.state, 'booked')
        self.assertEqual(booking.state, 'held')
        self.assertEqual(booking.passenger_name, 'Samir Kaci')
        self.assertEqual(second.state, 'waiting')
        booking.action_cancel()
        self.assertEqual(second.state, 'offered')

        reserved = self.env['transport.line'].create({
            'name': 'Réserve attente',
            'code': 'ATT-RSV',
            'seat_capacity': 1,
            'b2b_seat_reserve': 1,
            'release_hours': 2,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        held_bus = self.env['transport.departure'].create({
            'line_id': reserved.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=6),
            'release_hours': 2,
        })
        queued = Wait.join_public(
            held_bus.id, self.casa.id, self.rabat.id, 'Karim Boudiaf', '0555444000',
        )
        Wait.offer_open(held_bus)
        self.assertEqual(queued.state, 'waiting')

    def test_trip_costs_reduce_the_margin(self):
        line = self.env['transport.line'].create({
            'name': 'Charges',
            'code': 'CHARGE',
            'seat_capacity': 4,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 1000,
        })
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=6),
            'release_hours': 0,
        })
        booking = self.env['transport.booking'].book_public(
            departure.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111',
        )
        booking.pay_counter('cash')
        departure.write({
            'fuel_amount': 400,
            'toll_amount': 100,
            'driver_amount': 200,
        })
        self.assertEqual(departure.amount_collected, 1000)
        self.assertEqual(departure.amount_cost, 700)
        self.assertEqual(departure.amount_margin, 300)
        booking.action_cancel()
        departure.action_cancel()
        with self.assertRaises(UserError):
            departure.fuel_amount = 10

    def test_closing_a_day_cancels_open_departures_and_refunds(self):
        line = self.env['transport.line'].create({
            'name': 'Fermeture',
            'code': 'FERME',
            'seat_capacity': 1,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'cancel_hours': 24,
            'refund_percent': 100,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 1000,
        })
        today = fields.Datetime.now() + timedelta(hours=2)
        later = fields.Datetime.now() + timedelta(days=3)
        open_departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': today,
            'release_hours': 0,
        })
        running = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': today + timedelta(hours=3),
            'release_hours': 0,
        })
        running.write({'state': 'in_progress'})
        other_day = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': later,
            'release_hours': 0,
        })
        booking = self.env['transport.booking'].book_public(
            open_departure.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111',
            email='nora.close@example.dz',
        )
        booking.pay_counter('cash')
        queued = self.env['transport.waitlist'].join_public(
            open_departure.id, self.casa.id, self.rabat.id, 'Samir Kaci', '0555222000',
        )
        closed, kept = self.env['transport.departure'].close_service_day(
            open_departure._service_date(), 'Fête nationale', line,
        )
        self.assertIn(open_departure, closed)
        self.assertEqual(open_departure.state, 'cancelled')
        self.assertEqual(booking.state, 'cancelled')
        self.assertEqual(booking.refund_amount, 1000)
        self.assertEqual(booking.closure_reason, 'Fête nationale')
        self.assertEqual(booking.ticket_id.state, 'cancelled')
        self.assertEqual(queued.state, 'cancelled')
        self.assertEqual(running.state, 'in_progress')
        self.assertEqual(other_day.state, 'planned')
        self.assertTrue(self.env['mail.mail'].search_count([
            ('email_to', '=', 'nora.close@example.dz'),
            ('subject', 'ilike', 'annulé'),
        ]))
        self.assertFalse(kept)

    def test_company_statement_lists_subscriber_trips_for_the_period(self):
        line = self.env['transport.line'].create({
            'name': 'Relevé',
            'code': 'RELEVE',
            'seat_capacity': 4,
            'b2b_seat_reserve': 2,
            'release_hours': 0,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        company = self.env['res.partner'].create({'name': 'Cevital test', 'is_company': True})
        contract = self.env['transport.contract'].create({
            'partner_id': company.id,
            'line_ids': [(6, 0, [line.id])],
            'date_start': fields.Date.today() - timedelta(days=10),
            'seat_quota': 4,
        })
        contract.action_open()
        subscriber = self.env['transport.subscriber'].create({
            'name': 'Amine Zeroual',
            'contract_id': contract.id,
        })
        near = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=5),
            'release_hours': 0,
        })
        far = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(days=40),
            'release_hours': 0,
        })
        trip = near.book(self.casa, self.rabat, 1, '', subscriber=subscriber)
        trip.action_confirm()
        later = far.book(self.casa, self.rabat, 1, '', subscriber=subscriber)
        later.action_confirm()
        retail = near.book(self.casa, self.rabat, 1, 'Client Libre')
        retail.action_confirm()
        today = fields.Date.context_today(self.env.user)
        wizard = self.env['transport.contract.statement'].create({
            'partner_id': company.id,
            'date_from': today,
            'date_to': today,
        })
        statement = wizard.statement()
        self.assertEqual([row['name'] for row in statement['rows']], ['Amine Zeroual'])
        self.assertEqual(statement['seats'], 1)
        self.assertEqual(statement['boarded'], 0)
        self.assertNotIn(later.id, [row['id'] for row in statement['rows']])
        action = wizard.action_print()
        self.assertEqual(action['report_name'], 'transport.report_statement')

    def test_profit_demand_advice_and_gps(self):
        def make_line(code, capacity):
            return self.env['transport.line'].create({
                'name': code,
                'code': code,
                'seat_capacity': capacity,
                'b2b_seat_reserve': 0,
                'release_hours': 0,
                'stop_ids': [
                    (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                    (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
                ],
            })
        busy = make_line('DEMANDE', 2)
        quiet = make_line('CALME', 10)
        for line in (busy, quiet):
            self.env['transport.fare'].create({
                'line_id': line.id,
                'origin_stop_id': self.casa.id,
                'destination_stop_id': self.rabat.id,
                'price': 500,
            })
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Sprinter test'})
        model = self.env['fleet.vehicle.model'].create({'name': 'Court', 'brand_id': brand.id})
        small = self.env['fleet.vehicle'].create({
            'model_id': model.id,
            'license_plate': 'GPS-22',
        })
        small.seats = 2
        full = self.env['transport.departure'].create({
            'line_id': busy.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=4),
            'release_hours': 0,
        })
        empty = self.env['transport.departure'].create({
            'line_id': quiet.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=4),
            'release_hours': 0,
            'fuel_amount': 100,
        })
        sold = self.env['transport.booking'].book_public(
            full.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111', seat_count=2,
        )
        sold.pay_counter('cash')
        self.env['transport.waitlist'].join_public(
            full.id, self.casa.id, self.rabat.id, 'Samir Kaci', '0555111001',
        )
        self.env['transport.waitlist'].join_public(
            full.id, self.casa.id, self.rabat.id, 'Ines Kaci', '0555111002',
        )
        self.env['transport.booking'].book_public(
            empty.id, self.casa.id, self.rabat.id, 'Yanis Kaci', '0555111003',
        ).pay_counter('cash')
        today = fields.Date.context_today(self.env.user)
        insight = self.env['transport.insight'].create({
            'date_from': today,
            'date_to': today,
        })
        insight.action_compute()
        busy_row = insight.line_ids.filtered(lambda row: row.line_id == busy)
        quiet_row = insight.line_ids.filtered(lambda row: row.line_id == quiet)
        self.assertEqual(busy_row.margin, full.amount_margin)
        self.assertEqual(quiet_row.margin, empty.amount_margin)
        self.assertGreaterEqual(busy_row.fill_percent, 75)
        self.assertEqual(quiet_row.fill_percent, 10)
        texts = ' '.join(insight.advice_ids.mapped('summary'))
        self.assertIn('DEMANDE', texts)
        self.assertIn('CALME', texts)
        self.assertIn('2 places', texts)
        with self.assertRaises(UserError):
            empty.record_position(120, 3)
        mark = empty.record_position(36.75, 3.05)
        self.assertEqual(empty.last_latitude, mark.latitude)
        self.assertTrue(empty.track_token())

    def test_each_coach_keeps_its_own_alignment(self):
        cases = (
            ('coach_2_2_bench5', 49, 'bench'),
            ('coach_2_2_bench5', 45, 'bench'),
            ('coach_door_bench5', 55, 'door'),
            ('coach_courier_2_2', 49, 'courier'),
            ('coach_2_2', 40, 'pair'),
            ('minibus_2_1_bench4', 22, 'pair21'),
            ('midibus_2_2_rear2', 30, 'rear2'),
        )
        for layout, capacity, marker in cases:
            plan = self.env['transport.line'].build_seat_plan(layout, capacity, {1})
            seats = list(iter_plan_seats(plan))
            self.assertEqual([seat['number'] for seat in seats], list(range(1, capacity + 1)))
            self.assertFalse(seats[0]['free'])
            if marker == 'courier':
                self.assertEqual(plan['courier']['number'], 1)
            else:
                self.assertFalse(plan['courier'])
                row = plan['rows'][-1] if marker in ('bench', 'rear2') else plan['rows'][0]
                self.assertEqual(row['kind'], marker)

    def test_algeria_network_is_loaded_once(self):
        self.env['transport.line'].load_algeria_network()
        self.env['transport.line'].load_algeria_network()
        alger = self.env['transport.stop'].search([('code', '=', 'ALG')])
        self.assertEqual(len(alger), 1)
        self.assertEqual(alger.name, 'Alger')
        self.assertEqual(alger.city, 'Alger')
        codes = ['ALG-MED', 'ALG-ORN', 'ALG-CON', 'ALG-TIZ', 'ORN-TLM', 'CON-ANN', 'ALG-BEJ']
        lines = self.env['transport.line'].search([('code', 'in', codes)])
        self.assertEqual(len(lines), 7)
        self.assertGreater(
            self.env['transport.departure'].search_count([('line_id', 'in', lines.ids)]),
            7,
        )
        self.assertFalse(self.env['transport.line'].search([('code', '=', 'CASA-KEN')]))
        self.assertTrue(self.env['transport.contract'].search_count([('state', '=', 'open')]))
        self.assertTrue(self.env['transport.ticket'].search_count([]))

    def test_delay_keeps_a_departed_slot_on_sale_and_moves_the_day(self):
        self.env['transport.fare'].create({
            'line_id': self.line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 500,
        })
        missed = self.env['transport.departure'].create({
            'line_id': self.line.id,
            'departure_datetime': fields.Datetime.now() - timedelta(minutes=20),
            'release_hours': 0,
        })
        with self.assertRaises(UserError):
            self.env['transport.booking'].book_public(
                missed.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111',
            )
        missed.set_delay(90, 'Panne')
        self.assertFalse(missed.has_left())
        booking = self.env['transport.booking'].book_public(
            missed.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111',
        )
        self.assertEqual(booking.hold_until, missed.effective_datetime)
        missed.set_delay(120, 'Toujours en panne')
        self.assertEqual(booking.hold_until, missed.effective_datetime)

        night = self.env['transport.departure'].create({
            'line_id': self.line.id,
            'departure_datetime': fields.Datetime.from_string('2026-11-10 23:40:00'),
            'release_hours': 0,
        })
        self.assertEqual(str(night.service_date), '2026-11-10')
        night.set_delay(40, 'Route')
        self.assertEqual(str(night.service_date), '2026-11-11')

    def test_cancel_drops_the_waitlist_and_a_new_critical_check_blocks_start(self):
        line = self.env['transport.line'].create({
            'name': 'Annulation attente',
            'code': 'ANN-ATT',
            'seat_capacity': 1,
            'b2b_seat_reserve': 0,
            'release_hours': 0,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
            ],
        })
        self.env['transport.fare'].create({
            'line_id': line.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'price': 400,
        })
        departure = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=5),
            'release_hours': 0,
        })
        booking = self.env['transport.booking'].book_public(
            departure.id, self.casa.id, self.rabat.id, 'Nora Saidi', '0555000111',
        )
        queued = self.env['transport.waitlist'].join_public(
            departure.id, self.casa.id, self.rabat.id, 'Samir Kaci', '0555222000',
        )
        departure.action_cancel()
        self.assertEqual(departure.state, 'cancelled')
        self.assertEqual(booking.state, 'cancelled')
        self.assertEqual(queued.state, 'cancelled')

        fresh = self.make_departure()
        fresh.book(self.casa, self.rabat, 1, 'Yanis', seat_numbers=[4])
        with self.assertRaises(UserError):
            fresh.seat_capacity = 3
        self.assertEqual(fresh.seat_capacity, 4)

        company = self.env['res.partner'].create({'name': 'Atlas pay', 'is_company': True})
        contract = self.env['transport.contract'].create({
            'partner_id': company.id,
            'line_ids': [(6, 0, self.line.ids)],
            'date_start': fields.Date.context_today(self.line) - timedelta(days=1),
            'seat_quota': 2,
        })
        contract.action_open()
        subscriber = self.env['transport.subscriber'].create({
            'name': 'Karim pay',
            'contract_id': contract.id,
        })
        company_seat = fresh.book(self.casa, self.rabat, 1, '', subscriber=subscriber)
        with self.assertRaises(UserError):
            company_seat.pay_online()
        self.assertEqual(company_seat.state, 'held')
        self.assertFalse(company_seat.paid)

        self._open_boarding(fresh)
        fresh.check_ids.write({'result': 'ok'})
        self.env['transport.check.template'].create({
            'name': 'Extincteur test',
            'critical': True,
        })
        with self.assertRaises(UserError) as caught:
            fresh.action_start()
        self.assertIn('Extincteur test', caught.exception.args[0])

    def test_schedule_without_a_user_timezone_stays_in_algiers(self):
        saved = self.env.user.tz
        self.env.user.tz = False
        self.env.company.partner_id.tz = False
        schedule = self.env['transport.schedule'].create({
            'name': 'Huit heures',
            'line_id': self.line.id,
            'time_departure': 8.0,
        })
        moment = schedule.as_datetime(fields.Date.from_string('2026-06-15'))
        self.env.user.tz = saved
        self.assertEqual(fields.Datetime.to_string(moment), '2026-06-15 07:00:00')

    def _qualified_driver(self, name, line, day):
        driver = self.env['hr.employee'].create({
            'name': name,
            'company_id': line.company_id.id,
        })
        for doc_type in ('license', 'medical', 'training'):
            self.env['transport.driver.document'].create({
                'employee_id': driver.id,
                'doc_type': doc_type,
                'expires_on': day + timedelta(days=60),
            })
        self.env['transport.driver.route'].create({
            'employee_id': driver.id,
            'line_id': line.id,
        })
        return driver

    def _sized_vehicle(self, seats, plate, company):
        vehicle = self._vehicle(seats, plate)
        vehicle.write({'company_id': company.id, 'seats': seats})
        return vehicle

    def test_auto_assign_matches_bus_size_and_rotates_drivers(self):
        company = self.env['res.company'].create({'name': 'Auto Trans'})
        short = self.env['transport.line'].create({
            'name': 'Court',
            'code': 'AUTO-C',
            'company_id': company.id,
            'seat_capacity': 20,
            'average_speed': 70,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10, 'distance_km': 0}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20, 'distance_km': 100}),
            ],
        })
        self.assertEqual(short.route_length, 'short')
        self.assertAlmostEqual(short.drive_hours, 1.43, places=2)
        day = fields.Date.context_today(short) + timedelta(days=2)
        noon = fields.Datetime.from_string('%s 10:00:00' % day)
        departure = self.env['transport.departure'].create({
            'line_id': short.id,
            'departure_datetime': noon,
        })
        self._qualified_driver('Chauffeur court', short, day)
        large = self._sized_vehicle(49, 'AUTO-L', company)
        small = self._sized_vehicle(22, 'AUTO-S', company)
        self.assertEqual(large.bus_size, 'large')
        self.assertEqual(small.bus_size, 'small')
        departure.action_auto_assign()
        self.assertEqual(departure.vehicle_id, small)
        self.assertEqual(departure.state, 'assigned')
        self.assertEqual(departure.seat_capacity, 20)

        long = self.env['transport.line'].create({
            'name': 'Long',
            'code': 'AUTO-L',
            'company_id': company.id,
            'seat_capacity': 49,
            'average_speed': 70,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10, 'distance_km': 0}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20, 'distance_km': 420}),
            ],
        })
        self.assertEqual(long.route_length, 'long')
        self.assertAlmostEqual(long.drive_hours, 6.0)
        first_driver = self._qualified_driver('Karim long', long, day)
        second_driver = self._qualified_driver('Amina long', long, day)
        schedule = self.env['transport.schedule'].create({
            'name': 'Aube',
            'line_id': long.id,
            'time_departure': 6.0,
        })
        first = self.env['transport.departure'].create({
            'line_id': long.id,
            'schedule_id': schedule.id,
            'departure_datetime': noon,
        })
        second = self.env['transport.departure'].create({
            'line_id': long.id,
            'schedule_id': schedule.id,
            'departure_datetime': noon + timedelta(days=1),
        })
        (first | second).action_auto_assign()
        self.assertEqual(first.vehicle_id, large)
        self.assertEqual(second.vehicle_id, large)
        self.assertNotEqual(first.driver_id, second.driver_id)
        self.assertEqual({first.driver_id, second.driver_id}, {first_driver, second_driver})

        tight = self.env['transport.line'].create({
            'name': 'Chevauchement',
            'code': 'AUTO-H',
            'company_id': company.id,
            'seat_capacity': 49,
            'average_speed': 70,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10, 'distance_km': 0}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20, 'distance_km': 420}),
            ],
        })
        self._qualified_driver('Chauffeur seul', tight, day)
        self._sized_vehicle(49, 'AUTO-SEUL', company)
        morning = self.env['transport.departure'].create({
            'line_id': tight.id,
            'departure_datetime': noon,
        })
        evening = self.env['transport.departure'].create({
            'line_id': tight.id,
            'departure_datetime': noon + timedelta(hours=1),
        })
        morning.action_auto_assign()
        with self.assertRaises(UserError):
            evening.action_auto_assign()
        later = self.env['transport.departure'].create({
            'line_id': tight.id,
            'departure_datetime': noon + timedelta(hours=10),
        })
        with self.assertRaises(UserError):
            later.action_auto_assign()

    def _open_boarding(self, departure):
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Irisbus'})
        model = self.env['fleet.vehicle.model'].create({
            'name': 'Crossway %s' % departure.id,
            'brand_id': brand.id,
        })
        vehicle = self.env['fleet.vehicle'].create({
            'model_id': model.id,
            'license_plate': 'B-%s' % departure.id,
        })
        vehicle.seats = 20
        driver = self.env['hr.employee'].create({'name': 'Chauffeur %s' % departure.id})
        expires = departure._service_date() + timedelta(days=60)
        for doc_type in ('license', 'medical', 'training'):
            self.env['transport.driver.document'].create({
                'employee_id': driver.id,
                'doc_type': doc_type,
                'expires_on': expires,
            })
        departure.write({
            'vehicle_id': vehicle.id,
            'driver_id': driver.id,
            'seat_capacity': departure.seat_capacity,
        })
        departure.action_assign()
        departure.action_open_boarding()
        return departure
