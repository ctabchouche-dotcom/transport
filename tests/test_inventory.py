# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTransportInventory(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = 'UTC'
        cls.casa = cls.env['transport.stop'].create({
            'name': 'Alger', 'code': 'T-ALG', 'city': 'Alger',
        })
        cls.rabat = cls.env['transport.stop'].create({
            'name': 'Blida', 'code': 'T-BLI', 'city': 'Blida',
        })
        cls.kenitra = cls.env['transport.stop'].create({
            'name': 'Médéa', 'code': 'T-MED', 'city': 'Médéa',
        })
        cls.sale = cls.env['transport.stop'].create({
            'name': 'Chlef', 'code': 'T-CHF', 'city': 'Chlef',
        })

    def make_line(self, code, capacity=4, reserve=0, release_hours=2):
        return self.env['transport.line'].create({
            'name': code,
            'code': code,
            'seat_capacity': capacity,
            'b2b_seat_reserve': reserve,
            'release_hours': release_hours,
            'stop_ids': [
                (0, 0, {'stop_id': self.casa.id, 'sequence': 10}),
                (0, 0, {'stop_id': self.rabat.id, 'sequence': 20}),
                (0, 0, {'stop_id': self.kenitra.id, 'sequence': 30, 'boarding': False}),
            ],
        })

    def make_departure(self, line, hours=30, **extra):
        vals = {
            'line_id': line.id,
            'departure_datetime': fields.Datetime.now() + timedelta(hours=hours),
        }
        vals.update(extra)
        return self.env['transport.departure'].create(vals)

    def subscriber(self, line, name, quota=10):
        company = self.env['res.partner'].create({'name': name, 'is_company': True})
        contract = self.env['transport.contract'].create({
            'partner_id': company.id,
            'line_ids': [(6, 0, line.ids)],
            'date_start': fields.Date.context_today(line) - timedelta(days=1),
            'seat_quota': quota,
        })
        contract.action_open()
        return self.env['transport.subscriber'].create({
            'name': name,
            'contract_id': contract.id,
        })

    def test_a_seat_frees_on_the_next_hop(self):
        line = self.make_line('SEG', capacity=1, reserve=0)
        departure = self.make_departure(line)
        self.assertEqual(len(departure.leg_ids), 2)
        first = departure.book(self.casa, self.rabat, 1, 'Amina', channel='b2c')
        second = departure.book(self.rabat, self.kenitra, 1, 'Youssef', channel='b2c')
        self.assertEqual(first.state, 'held')
        self.assertEqual(second.state, 'held')
        with self.assertRaises(UserError):
            departure.book(self.casa, self.kenitra, 1, 'Sara', channel='b2c')
        with self.assertRaises(UserError):
            departure.book(self.casa, self.rabat, 1, 'Sara', channel='b2c')

    def test_company_reserve_blocks_individual_sales_until_release(self):
        line = self.make_line('RSV', capacity=2, reserve=1, release_hours=2)
        departure = self.make_departure(line, hours=30)
        self.assertGreater(departure.release_datetime, fields.Datetime.now())
        departure.book(self.casa, self.kenitra, 1, 'Amina', channel='b2c')
        with self.assertRaises(UserError):
            departure.book(self.casa, self.rabat, 1, 'Sara', channel='b2c')
        departure.book(self.casa, self.rabat, 1, 'Karim', subscriber=self.subscriber(line, 'Karim'))
        with self.assertRaises(UserError):
            departure.book(self.casa, self.kenitra, 1, 'Omar', subscriber=self.subscriber(line, 'Omar'))

        full = self.make_departure(line, hours=40)
        full.book(
            self.casa, self.kenitra, 2, 'Société Atlas',
            subscriber=self.subscriber(line, 'Atlas', quota=2),
        )
        with self.assertRaises(UserError):
            full.book(self.rabat, self.kenitra, 1, 'Sara', channel='b2c')

    def test_released_reserve_goes_back_to_individual_sales(self):
        line = self.make_line('REL', capacity=2, reserve=2, release_hours=24)
        departure = self.make_departure(line, hours=1)
        self.assertLess(departure.release_datetime, fields.Datetime.now())
        booking = departure.book(self.casa, self.kenitra, 2, 'Amina', channel='b2c')
        booking.action_confirm()
        self.assertEqual(booking.state, 'confirmed')
        self.assertEqual(departure.seats_taken, 2)

    def test_cancel_and_expired_hold_free_the_seat(self):
        line = self.make_line('HOLD', capacity=1, reserve=0)
        departure = self.make_departure(line)
        booking = departure.book(self.casa, self.rabat, 1, 'Amina')
        with self.assertRaises(UserError):
            departure.book(self.casa, self.rabat, 1, 'Sara')
        booking.action_cancel()
        replacement = departure.book(self.casa, self.rabat, 1, 'Sara')
        self.assertEqual(replacement.state, 'held')

        self.env.cr.execute(
            "UPDATE transport_booking SET hold_until = %s WHERE id = %s",
            [fields.Datetime.now() - timedelta(minutes=1), replacement.id],
        )
        replacement.invalidate_recordset()
        with self.assertRaises(UserError):
            replacement.action_confirm()
        taken = departure.book(self.casa, self.rabat, 1, 'Omar')
        self.env['transport.booking']._cron_expire_holds()
        self.assertEqual(replacement.state, 'cancelled')
        self.assertEqual(taken.state, 'held')
        taken.action_confirm()

    def test_one_create_cannot_oversell(self):
        line = self.make_line('BATCH', capacity=1, reserve=0)
        departure = self.make_departure(line)
        vals = {
            'departure_id': departure.id,
            'origin_stop_id': self.casa.id,
            'destination_stop_id': self.rabat.id,
            'seat_count': 1,
            'channel': 'b2c',
        }
        with self.assertRaises(UserError):
            self.env['transport.booking'].create([
                dict(vals, passenger_name='Amina'),
                dict(vals, passenger_name='Sara'),
            ])
        self.assertFalse(departure.booking_ids)

    def test_generation_is_idempotent_and_a_cancelled_slot_can_be_reused(self):
        line = self.make_line('GEN', capacity=10, reserve=0)
        self.env['transport.schedule'].create({
            'name': 'Matin',
            'line_id': line.id,
            'time_departure': 8.0,
        })
        start = fields.Date.context_today(line) + timedelta(days=1)
        created = line.generate_departures(start, start + timedelta(days=2))
        self.assertEqual(len(created), 3)
        self.assertEqual(len(created[0].leg_ids), 2)
        self.assertTrue(created[0].name.startswith('DEP/'))
        again = line.generate_departures(start, start + timedelta(days=2))
        self.assertFalse(again)

        departure = created[0]
        with self.assertRaises(UserError):
            self.env['transport.departure'].create({
                'line_id': line.id,
                'departure_datetime': departure.departure_datetime,
            })
        held = departure.book(self.casa, self.kenitra, 1, 'Amina')
        held.action_confirm()
        with self.assertRaises(UserError):
            departure.action_cancel()
        held.action_cancel()
        departure.action_cancel()
        self.assertEqual(departure.state, 'cancelled')
        reused = self.env['transport.departure'].create({
            'line_id': line.id,
            'departure_datetime': departure.departure_datetime,
        })
        self.assertEqual(reused.state, 'planned')

    def test_line_stops_freeze_when_a_departure_exists(self):
        line = self.make_line('LOCK')
        rabat = line.stop_ids.filtered(lambda stop: stop.stop_id == self.rabat)
        rabat.boarding = False
        departure = self.make_departure(line)
        with self.assertRaises(UserError):
            departure.book(self.rabat, self.kenitra, 1, 'Amina')
        with self.assertRaises(UserError):
            self.env['transport.line.stop'].create({
                'line_id': line.id,
                'stop_id': self.sale.id,
                'sequence': 15,
            })
        departure.book(self.casa, self.kenitra, 1, 'Amina')

    def test_assign_bus_then_capacity_cannot_drop_below_sales(self):
        line = self.make_line('BUS', capacity=4, reserve=0)
        departure = self.make_departure(line)
        departure.book(self.casa, self.kenitra, 3, 'Groupe', channel='b2c').action_confirm()
        with self.assertRaises(UserError):
            departure.seat_capacity = 2
        self.assertEqual(departure.seat_capacity, 4)

        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Irisbus'})
        model = self.env['fleet.vehicle.model'].create({'name': 'Crossway', 'brand_id': brand.id})
        vehicle = self.env['fleet.vehicle'].create({
            'model_id': model.id,
            'license_plate': '12345-A-6',
        })
        vehicle.seats = 10
        driver = self.env['hr.employee'].create({'name': 'Karim El Fassi'})
        with self.assertRaises(UserError):
            departure.action_assign()
        departure.write({'vehicle_id': vehicle.id, 'driver_id': driver.id})
        with self.assertRaises(UserError):
            departure.action_assign()
        expires = departure._service_date() + timedelta(days=30)
        for doc_type in ('license', 'medical', 'training'):
            self.env['transport.driver.document'].create({
                'employee_id': driver.id,
                'doc_type': doc_type,
                'reference': doc_type,
                'expires_on': expires,
            })
        self.assertEqual(departure.seat_capacity, 10)
        self.assertEqual(set(departure.leg_ids.mapped('seat_capacity')), {10})
        departure.action_assign()
        departure.action_open_boarding()
        self.assertEqual(len(departure.check_ids), 4)
        with self.assertRaises(UserError):
            departure.action_start()
        departure.check_ids.write({'result': 'ok'})
        departure.action_start()
        with self.assertRaises(UserError):
            departure.book(self.casa, self.rabat, 1, 'Retardataire')
        departure.action_done()
        self.assertEqual(departure.state, 'done')
