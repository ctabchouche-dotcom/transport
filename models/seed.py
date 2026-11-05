# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

STOPS = [
    ('ALG', 'Alger', 'Alger'),
    ('BLI', 'Blida', 'Blida'),
    ('MED', 'Médéa', 'Médéa'),
    ('CHF', 'Chlef', 'Chlef'),
    ('ORN', 'Oran', 'Oran'),
    ('SET', 'Sétif', 'Sétif'),
    ('CON', 'Constantine', 'Constantine'),
    ('TIZ', 'Tizi Ouzou', 'Tizi Ouzou'),
    ('BEJ', 'Béjaïa', 'Béjaïa'),
    ('SBA', 'Sidi Bel Abbès', 'Sidi Bel Abbès'),
    ('TLM', 'Tlemcen', 'Tlemcen'),
    ('ANN', 'Annaba', 'Annaba'),
]

LINES = [
    {
        'code': 'ALG-MED', 'name': 'Alger - Médéa', 'line_type': 'hybrid',
        'seat_capacity': 49, 'seat_layout': 'coach_2_2_bench5',
        'b2b_seat_reserve': 12, 'release_hours': 2, 'fare': 800,
        'stops': [('ALG', 0), ('BLI', 50), ('MED', 60)],
        'fares': [('ALG', 'BLI', 400), ('BLI', 'MED', 450), ('ALG', 'MED', 800)],
        'schedules': [('Matin', 7.5, 'all'), ('Soir', 16.5, 'all')],
    },
    {
        'code': 'ALG-ORN', 'name': 'Alger - Oran', 'line_type': 'hybrid',
        'seat_capacity': 55, 'seat_layout': 'coach_door_bench5',
        'b2b_seat_reserve': 10, 'release_hours': 3, 'fare': 2200,
        'stops': [('ALG', 0), ('CHF', 200), ('ORN', 220)],
        'fares': [('ALG', 'CHF', 1200), ('CHF', 'ORN', 1100), ('ALG', 'ORN', 2200)],
        'schedules': [('Aube', 6.0, 'all'), ('Après-midi', 14.0, 'all')],
    },
    {
        'code': 'ALG-CON', 'name': 'Alger - Constantine', 'line_type': 'b2c',
        'seat_capacity': 49, 'seat_layout': 'coach_courier_2_2',
        'b2b_seat_reserve': 0, 'release_hours': 0, 'fare': 1800,
        'stops': [('ALG', 0), ('SET', 300), ('CON', 120)],
        'fares': [('ALG', 'SET', 1000), ('SET', 'CON', 900), ('ALG', 'CON', 1800)],
        'schedules': [('Nuit', 21.0, 'all'), ('Matin', 8.0, 'week')],
    },
    {
        'code': 'ALG-TIZ', 'name': 'Navette Alger - Tizi Ouzou', 'line_type': 'b2b',
        'seat_capacity': 22, 'seat_layout': 'minibus_2_1_bench4',
        'b2b_seat_reserve': 22, 'release_hours': 1,
        'stops': [('ALG', 0), ('TIZ', 105)],
        'schedules': [('Aller', 7.0, 'week'), ('Retour', 17.5, 'week')],
    },
    {
        'code': 'ORN-TLM', 'name': 'Oran - Tlemcen', 'line_type': 'hybrid',
        'seat_capacity': 45, 'seat_layout': 'coach_2_2_bench5',
        'b2b_seat_reserve': 8, 'release_hours': 2, 'fare': 900,
        'stops': [('ORN', 0), ('SBA', 80), ('TLM', 90)],
        'fares': [('ORN', 'SBA', 500), ('SBA', 'TLM', 450), ('ORN', 'TLM', 900)],
        'schedules': [('Matin', 8.5, 'all'), ('Soir', 18.0, 'all')],
    },
    {
        'code': 'CON-ANN', 'name': 'Constantine - Annaba', 'line_type': 'b2c',
        'seat_capacity': 40, 'seat_layout': 'coach_2_2',
        'b2b_seat_reserve': 0, 'release_hours': 0, 'fare': 700,
        'stops': [('CON', 0), ('ANN', 150)],
        'fares': [('CON', 'ANN', 700)],
        'schedules': [('Matin', 9.0, 'all'), ('Après-midi', 15.0, 'all')],
    },
    {
        'code': 'ALG-BEJ', 'name': 'Alger - Béjaïa', 'line_type': 'hybrid',
        'seat_capacity': 30, 'seat_layout': 'midibus_2_2_rear2',
        'b2b_seat_reserve': 6, 'release_hours': 2, 'fare': 1200,
        'stops': [('ALG', 0), ('TIZ', 105), ('BEJ', 140)],
        'fares': [('ALG', 'TIZ', 700), ('TIZ', 'BEJ', 600), ('ALG', 'BEJ', 1200)],
        'schedules': [('Matin', 8.0, 'all')],
    },
]

VEHICLES = [
    ('Mercedes', 'Tourismo', '00116-116-16', 49, 'coach_2_2_bench5'),
    ('Irisbus', 'Crossway', '00231-116-31', 55, 'coach_door_bench5'),
    ('Mercedes', 'Sprinter', '00316-116-16', 22, 'minibus_2_1_bench4'),
    ('Iveco', 'Evadys', '00416-116-16', 45, 'coach_2_2_bench5'),
    ('Mercedes', 'Tourismo', '00516-116-16', 49, 'coach_courier_2_2'),
    ('Iveco', 'Crossway Pop', '00616-116-16', 40, 'coach_2_2'),
    ('Hyundai', 'County', '00716-116-16', 30, 'midibus_2_2_rear2'),
]

DRIVERS = ['Karim Boudiaf', 'Amina Cherif', 'Yacine Meziane', 'Sarah Belkacem']


class TransportLineSeed(models.Model):
    _inherit = 'transport.line'

    @api.model
    def load_algeria_network(self):
        self._archive_morocco_sample()
        stops = self._ensure_algeria_stops()
        lines = self._ensure_algeria_lines(stops)
        vehicles = self._ensure_algeria_vehicles()
        drivers = self._ensure_algeria_drivers()
        self._ensure_driver_routes(lines, drivers)
        contracts = self._ensure_algeria_contracts(lines)
        self._ensure_algeria_departures(lines, vehicles, drivers, contracts)
        self.env['transport.booking']._assign_missing_seats()
        _logger.info(
            "Réseau Algérie : %s lignes, %s départs.",
            len(lines),
            self.env['transport.departure'].search_count([('line_id', 'in', lines.ids)]),
        )
        return True

    @api.model
    def _archive_morocco_sample(self):
        lines = self.with_context(active_test=False).search([('code', '=', 'CASA-KEN')])
        if lines:
            lines.write({'active': False})
        stops = self.env['transport.stop'].with_context(active_test=False).search([
            ('code', 'in', ['CASA', 'RABAT', 'KENITRA']),
        ])
        if stops:
            stops.write({'active': False})

    @api.model
    def _ensure_algeria_stops(self):
        stops = {}
        Stop = self.env['transport.stop'].with_context(active_test=False)
        for code, name, city in STOPS:
            stop = Stop.search([('code', '=', code)], limit=1)
            if not stop:
                stop = Stop.create({'name': name, 'code': code, 'city': city})
            elif not stop.active:
                stop.active = True
            stops[code] = stop
        return stops

    @api.model
    def _ensure_algeria_lines(self, stops):
        lines = self.env['transport.line']
        Line = self.with_context(active_test=False)
        for spec in LINES:
            line = Line.search([('code', '=', spec['code'])], limit=1)
            if not line:
                line = self.create({
                    'name': spec['name'],
                    'code': spec['code'],
                    'line_type': spec['line_type'],
                    'seat_capacity': spec['seat_capacity'],
                    'seat_layout': spec.get('seat_layout'),
                    'b2b_seat_reserve': spec['b2b_seat_reserve'],
                    'release_hours': spec['release_hours'],
                    'fare': spec.get('fare') or 0,
                })
                sequence = 10
                for code, distance in spec['stops']:
                    self.env['transport.line.stop'].create({
                        'line_id': line.id,
                        'stop_id': stops[code].id,
                        'sequence': sequence,
                        'distance_km': distance,
                    })
                    sequence += 10
            elif not line.active:
                line.active = True
            if spec.get('seat_layout') and not line.seat_layout:
                line.seat_layout = spec['seat_layout']
            self._ensure_fares(line, stops, spec.get('fares') or [])
            for name, hour, days in spec['schedules']:
                self._ensure_schedule(line, name, hour, days)
            lines |= line
        return lines

    @api.model
    def _ensure_fares(self, line, stops, pairs):
        Fare = self.env['transport.fare']
        for origin_code, destination_code, price in pairs:
            fare = Fare.search([
                ('line_id', '=', line.id),
                ('origin_stop_id', '=', stops[origin_code].id),
                ('destination_stop_id', '=', stops[destination_code].id),
            ], limit=1)
            if not fare:
                Fare.create({
                    'line_id': line.id,
                    'origin_stop_id': stops[origin_code].id,
                    'destination_stop_id': stops[destination_code].id,
                    'price': price,
                })
            elif not fare.price:
                fare.price = price

    @api.model
    def _ensure_schedule(self, line, name, hour, days):
        schedule = self.env['transport.schedule'].search([
            ('line_id', '=', line.id),
            ('name', '=', name),
        ], limit=1)
        if schedule:
            return schedule
        week = days in ('all', 'week')
        weekend = days == 'all'
        return self.env['transport.schedule'].create({
            'name': name,
            'line_id': line.id,
            'time_departure': hour,
            'mon': week, 'tue': week, 'wed': week, 'thu': week, 'fri': week,
            'sat': weekend, 'sun': weekend,
        })

    @api.model
    def _ensure_algeria_vehicles(self):
        vehicles = self.env['fleet.vehicle']
        Brand = self.env['fleet.vehicle.model.brand']
        Model = self.env['fleet.vehicle.model']
        for brand_name, model_name, plate, seats, layout in VEHICLES:
            vehicle = self.env['fleet.vehicle'].search([('license_plate', '=', plate)], limit=1)
            if not vehicle:
                brand = Brand.search([('name', '=', brand_name)], limit=1)
                if not brand:
                    brand = Brand.create({'name': brand_name})
                model = Model.search([
                    ('name', '=', model_name),
                    ('brand_id', '=', brand.id),
                ], limit=1)
                if not model:
                    model = Model.create({'name': model_name, 'brand_id': brand.id})
                vehicle = self.env['fleet.vehicle'].create({
                    'model_id': model.id,
                    'license_plate': plate,
                    'seat_layout': layout,
                })
            if not vehicle.seat_layout:
                vehicle.seat_layout = layout
            vehicle.seats = seats
            vehicles |= vehicle
        return vehicles

    @api.model
    def _ensure_algeria_drivers(self):
        drivers = self.env['hr.employee']
        Document = self.env['transport.driver.document']
        expires = fields.Date.context_today(self) + timedelta(days=400)
        for name in DRIVERS:
            driver = self.env['hr.employee'].search([('name', '=', name)], limit=1)
            if not driver:
                driver = self.env['hr.employee'].create({'name': name})
            for doc_type, reference in (
                ('license', 'DZ-%s' % driver.id),
                ('medical', 'MED-%s' % driver.id),
                ('training', 'FOR-%s' % driver.id),
            ):
                document = Document.search([
                    ('employee_id', '=', driver.id),
                    ('doc_type', '=', doc_type),
                ], limit=1)
                if not document:
                    Document.create({
                        'employee_id': driver.id,
                        'doc_type': doc_type,
                        'reference': reference,
                        'expires_on': expires,
                    })
                elif document.expires_on < expires:
                    document.expires_on = expires
            drivers |= driver
        return drivers

    @api.model
    def _ensure_driver_routes(self, lines, drivers):
        """Each sample driver keeps one line. Existing choices are left as they are."""
        wanted = {
            'Karim Boudiaf': 'ALG-ORN',
            'Amina Cherif': 'ALG-CON',
            'Yacine Meziane': 'ORN-TLM',
            'Sarah Belkacem': 'ALG-TIZ',
        }
        by_code = {line.code: line for line in lines}
        Route = self.env['transport.driver.route']
        for driver in drivers:
            if Route.search_count([('employee_id', '=', driver.id)]):
                continue
            code = wanted.get(driver.name)
            line = by_code.get(code)
            if not line:
                continue
            Route.create({'employee_id': driver.id, 'line_id': line.id})

    @api.model
    def _ensure_algeria_contracts(self, lines):
        by_code = {line.code: line for line in lines}
        specs = [
            ('Sonatrach', 'open', 'ALG-TIZ', 12, ['Amine Zeroual', 'Nadia Hamidi', 'Farid Saadi', 'Lina Hadj']),
            ('Cevital', 'open', 'ORN-TLM', 8, ['Riad Mansouri', 'Ines Kaci', 'Mehdi Bouzid']),
            ('Algérie Télécom', 'draft', 'ALG-MED', 6, ['Houda Belhadj', 'Walid Cherifi']),
            ('Air Algérie', 'closed', 'ALG-ORN', 4, ['Samir Khelifi']),
        ]
        contracts = {}
        for company_name, state, line_code, quota, people in specs:
            partner = self.env['res.partner'].search([
                ('name', '=', company_name),
                ('is_company', '=', True),
            ], limit=1)
            if not partner:
                partner = self.env['res.partner'].create({
                    'name': company_name,
                    'is_company': True,
                })
            line = by_code[line_code]
            contract = self.env['transport.contract'].search([
                ('partner_id', '=', partner.id),
                ('line_ids', 'in', line.id),
            ], limit=1)
            if not contract:
                contract = self.env['transport.contract'].create({
                    'partner_id': partner.id,
                    'line_ids': [(6, 0, [line.id])],
                    'date_start': fields.Date.context_today(self) - timedelta(days=30),
                    'date_end': fields.Date.context_today(self) + timedelta(days=365),
                    'seat_quota': quota,
                })
            if state in ('open', 'closed') and contract.state == 'draft':
                contract.action_open()
            if state == 'closed' and contract.state == 'open':
                contract.action_close()
            for person in people:
                if not self.env['transport.subscriber'].search_count([
                    ('name', '=', person),
                    ('contract_id', '=', contract.id),
                ]):
                    self.env['transport.subscriber'].create({
                        'name': person,
                        'contract_id': contract.id,
                    })
            contracts[company_name] = contract
        return contracts

    @api.model
    def _ensure_algeria_departures(self, lines, vehicles, drivers, contracts):
        start = fields.Date.context_today(self)
        end = start + timedelta(days=6)
        for line in lines:
            line.with_context(tz='Africa/Algiers').generate_departures(start, end)
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param('transport.algeria_ops_ready'):
            return
        by_code = {line.code: line for line in lines}
        pool = self._departures_by_line(lines)
        self._seed_sales(pool[by_code['ALG-MED'].id])
        self._seed_assigned(pool[by_code['ALG-ORN'].id], vehicles[1], drivers[0])
        self._seed_boarding(pool[by_code['ALG-CON'].id], vehicles[0], drivers[1])
        self._seed_shuttle(pool[by_code['ALG-TIZ'].id], contracts['Sonatrach'])
        self._seed_running(pool[by_code['ORN-TLM'].id], vehicles[3], drivers[2])
        self._seed_done(pool[by_code['CON-ANN'].id], vehicles[1], drivers[3])
        self._seed_cancelled(pool[by_code['ALG-BEJ'].id])
        params.set_param('transport.algeria_ops_ready', '1')

    @api.model
    def _departures_by_line(self, lines):
        grouped = {}
        departures = self.env['transport.departure'].search([
            ('line_id', 'in', lines.ids),
            ('state', '!=', 'cancelled'),
        ], order='departure_datetime, id')
        for departure in departures:
            bucket = grouped.setdefault(departure.line_id.id, self.env['transport.departure'])
            grouped[departure.line_id.id] = bucket | departure
        for line in lines:
            grouped.setdefault(line.id, self.env['transport.departure'])
        return grouped

    def _trip(self, departure):
        stops = departure.line_id.stop_ids.sorted('sequence')
        return stops[0].stop_id, stops[-1].stop_id

    def _seed_booking(self, departure, passenger, partner=None, subscriber=None):
        existing = self.env['transport.booking'].search([
            ('departure_id', '=', departure.id),
            ('passenger_name', '=', passenger),
        ], limit=1)
        if existing:
            return existing
        origin, destination = self._trip(departure)
        return departure.book(
            origin, destination, 1, passenger,
            partner=partner, subscriber=subscriber,
        )

    def _seed_sales(self, departures):
        departure = departures[:1]
        if not departure or departure.state != 'planned':
            return
        partner = self.env['res.partner'].search([('email', '=', 'lina.hadj@example.dz')], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name': 'Lina Hadj',
                'email': 'lina.hadj@example.dz',
            })
        held = self._seed_booking(departure, 'Riad Mansouri')
        confirmed = self._seed_booking(departure, 'Lina Hadj', partner=partner)
        if confirmed.state == 'held':
            confirmed.action_confirm()
        if held.state == 'held' and departures[1:2]:
            return

    def _crew(self, departure, vehicle, driver):
        if departure.state != 'planned':
            return
        departure.write({
            'vehicle_id': vehicle.id,
            'driver_id': driver.id,
            'seat_capacity': departure.seat_capacity,
        })
        departure.action_assign()

    def _seed_assigned(self, departures, vehicle, driver):
        departure = departures[:1]
        if departure and departure.state == 'planned':
            self._crew(departure, vehicle, driver)

    def _seed_boarding(self, departures, vehicle, driver):
        departure = departures[:1]
        if not departure or departure.state != 'planned':
            return
        booking = self._seed_booking(departure, 'Ines Kaci')
        if booking.state == 'held':
            booking.action_confirm()
        self._crew(departure, vehicle, driver)
        if departure.state == 'assigned':
            departure.action_open_boarding()

    def _seed_shuttle(self, departures, contract):
        departure = departures[:1]
        subscriber = contract.subscriber_ids[:1]
        if not departure or departure.state != 'planned' or not subscriber or contract.state != 'open':
            return
        booking = self._seed_booking(departure, subscriber.name, subscriber=subscriber)
        if booking.state == 'held':
            booking.action_confirm()

    def _seed_running(self, departures, vehicle, driver):
        departure = departures[:1]
        if not departure or departure.state != 'planned':
            return
        boarded = self._seed_booking(departure, 'Mehdi Bouzid')
        absent = self._seed_booking(departure, 'Farid Saadi')
        if boarded.state == 'held':
            boarded.action_confirm()
        if absent.state == 'held':
            absent.action_confirm()
        self._crew(departure, vehicle, driver)
        if departure.state == 'assigned':
            departure.action_open_boarding()
        departure.check_ids.write({'result': 'ok'})
        if boarded.state == 'confirmed' and boarded.channel == 'b2c' and not boarded.paid:
            boarded.pay_counter('cash')
        if boarded.state == 'confirmed':
            boarded.action_board()
        if absent.state == 'confirmed':
            absent.action_noshow()
        if departure.state == 'boarding':
            departure.action_start()

    def _seed_done(self, departures, vehicle, driver):
        departure = departures[:1]
        if not departure or departure.state != 'planned':
            return
        booking = self._seed_booking(departure, 'Houda Belhadj')
        if booking.state == 'held':
            booking.action_confirm()
        self._crew(departure, vehicle, driver)
        if departure.state == 'assigned':
            departure.action_open_boarding()
        departure.check_ids.write({'result': 'ok'})
        if booking.state == 'confirmed' and booking.channel == 'b2c' and not booking.paid:
            booking.pay_counter('cash')
        if booking.state == 'confirmed':
            booking.action_board()
        if departure.state == 'boarding':
            departure.action_start()
        if departure.state == 'in_progress':
            departure.action_done()

    def _seed_cancelled(self, departures):
        departure = departures[:1]
        if not departure or departure.state != 'planned':
            return
        other = departures[1:2]
        if other and other.state == 'planned':
            cancelled = self._seed_booking(other, 'Walid Cherifi')
            if cancelled.state == 'held':
                cancelled.action_confirm()
            if cancelled.state == 'confirmed':
                cancelled.action_cancel()
        departure.action_cancel()
