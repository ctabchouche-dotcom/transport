# -*- coding: utf-8 -*-
import hashlib
import hmac
from datetime import timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .crew import BUS_SIZES, LENGTH_TO_SIZE, MAX_DRIVE_HOURS, ROUTE_LENGTHS
from .qualification import DOCUMENT_TYPES


class TransportDeparture(models.Model):
    _name = 'transport.departure'
    _description = 'Départ'
    _inherit = ['mail.thread']
    _order = 'departure_datetime, id'

    name = fields.Char(string='Référence', required=True, copy=False, default='/', tracking=True)
    line_id = fields.Many2one(
        'transport.line', string='Ligne', required=True, ondelete='restrict', index=True, tracking=True,
    )
    schedule_id = fields.Many2one('transport.schedule', string='Horaire', ondelete='set null')
    company_id = fields.Many2one(
        'res.company', string='Société', required=True, default=lambda self: self.env.company,
    )
    departure_datetime = fields.Datetime(string='Départ', required=True, index=True, tracking=True)
    service_date = fields.Date(
        string='Jour', compute='_compute_service_date', store=True, index=True,
    )
    delay_minutes = fields.Integer(string='Retard (minutes)', default=0, tracking=True)
    delay_reason = fields.Char(string='Motif du retard', tracking=True)
    effective_datetime = fields.Datetime(
        string='Départ réel', compute='_compute_effective_datetime', store=True, index=True,
    )
    release_hours = fields.Integer(string='Libération (heures avant le départ)', default=2)
    release_datetime = fields.Datetime(
        string='Libération de la réserve',
        compute='_compute_release_datetime',
        store=True,
    )
    seat_capacity = fields.Integer(string='Capacité', required=True, tracking=True)
    seat_layout_label = fields.Char(string='Alignement', compute='_compute_seat_layout_label')
    b2b_seat_reserve = fields.Integer(string='Réserve entreprise', tracking=True)
    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Bus', tracking=True, check_company=True, ondelete='restrict',
    )
    device_position_url = fields.Char(related='vehicle_id.device_position_url', string='Adresse GPS')
    device_scan_url = fields.Char(related='vehicle_id.device_scan_url', string='Adresse du lecteur')
    driver_id = fields.Many2one(
        'hr.employee', string='Chauffeur', tracking=True, check_company=True, ondelete='restrict',
    )
    route_length = fields.Selection(related='line_id.route_length', string='Longueur')
    drive_hours = fields.Float(related='line_id.drive_hours', string='Conduite (h)')
    state = fields.Selection(
        [
            ('planned', 'Planifié'),
            ('assigned', 'Affecté'),
            ('boarding', 'Embarquement'),
            ('in_progress', 'En course'),
            ('done', 'Terminé'),
            ('cancelled', 'Annulé'),
        ],
        string='Statut',
        default='planned',
        required=True,
        tracking=True,
        index=True,
    )
    leg_ids = fields.One2many('transport.leg', 'departure_id', string='Tronçons')
    booking_ids = fields.One2many('transport.booking', 'departure_id', string='Réservations')
    waitlist_ids = fields.One2many('transport.waitlist', 'departure_id', string='Liste d\'attente')
    check_ids = fields.One2many('transport.departure.check', 'departure_id', string='Checklist')
    position_ids = fields.One2many('transport.position', 'departure_id', string='Positions')
    last_latitude = fields.Float(string='Latitude', compute='_compute_last_position', digits=(9, 6))
    last_longitude = fields.Float(string='Longitude', compute='_compute_last_position', digits=(9, 6))
    last_tracked_at = fields.Datetime(string='Dernière position', compute='_compute_last_position')
    seats_taken = fields.Integer(string='Prises (pic)', compute='_compute_seats_taken')
    seats_sold = fields.Integer(string='Places vendues', compute='_compute_result')
    amount_collected = fields.Float(
        string='Encaissé', compute='_compute_result',
        help="Somme des billets payés, en dinars. Ce n'est pas une écriture comptable.",
    )
    amount_refunded = fields.Float(string='Remboursé', compute='_compute_result')
    amount_net = fields.Float(string='Net', compute='_compute_result')
    fuel_amount = fields.Float(string='Gasoil', default=0, tracking=True)
    toll_amount = fields.Float(string='Péage', default=0, tracking=True)
    driver_amount = fields.Float(string='Indemnité chauffeur', default=0, tracking=True)
    amount_cost = fields.Float(
        string='Charges', compute='_compute_result',
        help="Gasoil, péage et indemnité, en dinars. Ce n'est pas une écriture comptable.",
    )
    amount_margin = fields.Float(string='Marge', compute='_compute_result')

    _delay_positive = models.Constraint(
        'CHECK(delay_minutes >= 0 AND delay_minutes <= 720)',
        'Le retard est compris entre 0 et 720 minutes.',
    )
    _capacity_positive = models.Constraint(
        'CHECK(seat_capacity > 0)',
        'La capacité doit être positive.',
    )
    _reserve_within_capacity = models.Constraint(
        'CHECK(b2b_seat_reserve >= 0 AND b2b_seat_reserve <= seat_capacity)',
        'La réserve entreprise doit tenir dans la capacité.',
    )
    _release_positive = models.Constraint(
        'CHECK(release_hours >= 0)',
        "Le délai de libération ne peut pas être négatif.",
    )
    _costs_positive = models.Constraint(
        'CHECK(fuel_amount >= 0 AND toll_amount >= 0 AND driver_amount >= 0)',
        'Les charges du départ ne peuvent pas être négatives.',
    )

    def init(self):
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS transport_departure_open_slot_idx
            ON transport_departure (line_id, departure_datetime)
            WHERE state IS DISTINCT FROM 'cancelled'
        """)

    @api.depends('effective_datetime')
    def _compute_service_date(self):
        for departure in self:
            departure.service_date = departure._service_date() if departure.departure_datetime else False

    @api.depends('departure_datetime', 'delay_minutes')
    def _compute_effective_datetime(self):
        for departure in self:
            base = departure.departure_datetime
            minutes = departure.delay_minutes or 0
            departure.effective_datetime = base + timedelta(minutes=minutes) if base else False

    @api.depends('position_ids.latitude', 'position_ids.longitude', 'position_ids.recorded_at')
    def _compute_last_position(self):
        for departure in self:
            last = departure.position_ids[:1]
            departure.last_latitude = last.latitude if last else 0.0
            departure.last_longitude = last.longitude if last else 0.0
            departure.last_tracked_at = last.recorded_at if last else False

    def track_token(self):
        self.ensure_one()
        digest = hmac.new(
            self.env['transport.ticket']._secret().encode(),
            f'track:{self.id}:{self.name}'.encode(),
            hashlib.sha256,
        ).hexdigest()[:24]
        return digest

    def track_path(self):
        self.ensure_one()
        return '/suivi-bus/%s/%s?db=%s' % (self.id, self.track_token(), self.env.cr.dbname)

    @api.model
    def _parse_coordinates(self, latitude, longitude):
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            raise UserError(_("Position GPS illisible."))
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise UserError(_("Position GPS hors limites."))
        return latitude, longitude

    def record_position(self, latitude, longitude):
        self.ensure_one()
        if self.state == 'cancelled':
            raise UserError(_("Ce départ est annulé."))
        latitude, longitude = self._parse_coordinates(latitude, longitude)
        return self.env['transport.position'].create({
            'departure_id': self.id,
            'vehicle_id': self.vehicle_id.id,
            'latitude': latitude,
            'longitude': longitude,
        })

    def action_open_tracking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.track_path(),
            'target': 'new',
        }

    def _local_time(self, moment):
        self.ensure_one()
        if not moment:
            return False
        company = self.company_id or self.env.company
        tzname = self.env.user.tz or company.partner_id.tz or 'Africa/Algiers'
        return pytz.UTC.localize(moment).astimezone(pytz.timezone(tzname))

    def stop_passage(self, stop):
        """Clock time at a stop: departure plus the distance already covered."""
        self.ensure_one()
        base = self.effective_datetime or self.departure_datetime
        if not base:
            return False
        speed = self.line_id.average_speed or 70
        cumulative = 0.0
        for line_stop in self.line_id.stop_ids.sorted('sequence'):
            cumulative += line_stop.distance_km or 0.0
            if line_stop.stop_id == stop:
                return base + timedelta(hours=cumulative / speed)
        return base

    def b2c_free_between(self, origin, destination):
        self.ensure_one()
        legs, _origin_sequence, _destination_sequence = self._legs_between(origin, destination)
        if not legs:
            return 0
        return min(leg.free_seats('b2c') for leg in legs)

    def passage_label(self, stop):
        self.ensure_one()
        local = self._local_time(self.stop_passage(stop))
        return local.strftime('%d/%m/%Y %H:%M') if local else ''

    def passage_rows(self):
        self.ensure_one()
        rows = []
        for line_stop in self.line_id.stop_ids.sorted('sequence'):
            local = self._local_time(self.stop_passage(line_stop.stop_id))
            rows.append({
                'name': line_stop.stop_id.name,
                'label': local.strftime('%d/%m/%Y %H:%M') if local else '',
                'hour': local.strftime('%H:%M') if local else '',
            })
        return rows

    def _live_bookings(self):
        now = fields.Datetime.now()
        return self.booking_ids.filtered(
            lambda booking: booking.state in ('confirmed', 'boarded') or (
                booking.state == 'held' and booking.hold_until and booking.hold_until > now
            ),
        )

    def set_delay(self, minutes, reason=None):
        for departure in self:
            if departure.state in ('done', 'cancelled'):
                raise UserError(_("Ce départ n'accepte plus de retard."))
            try:
                minutes = int(minutes)
            except (TypeError, ValueError):
                minutes = -1
            if minutes < 0 or minutes > 720:
                raise UserError(_("Le retard est compris entre 0 et 720 minutes."))
            reason = (reason or '').strip()
            previous = fields.Datetime.to_datetime(departure.effective_datetime)
            departure.write({
                'delay_minutes': minutes,
                'delay_reason': reason if minutes else False,
            })
            current = fields.Datetime.to_datetime(departure.effective_datetime)
            if previous and current and current > previous:
                holds = departure.booking_ids.filtered(
                    lambda booking: (
                        booking.state == 'held'
                        and fields.Datetime.to_datetime(booking.hold_until) == previous
                    ),
                )
                if holds:
                    holds.with_context(transport_extend_hold=True).write({'hold_until': current})
            if minutes:
                departure.message_post(body=_(
                    "Retard de %s min. Départ réel : %s. %s",
                    minutes,
                    fields.Datetime.to_string(departure.effective_datetime),
                    reason,
                ))
            else:
                departure.message_post(body=_("Retard annulé. Le départ revient à l'heure prévue."))
            departure._live_bookings()._notify('transport.email_template_delay')
        return True

    def swap_vehicle(self, vehicle):
        self.ensure_one()
        if self.state not in ('assigned', 'boarding'):
            raise UserError(_("Le bus se remplace pendant l'affectation ou l'embarquement."))
        if not vehicle:
            raise UserError(_("Choisissez le bus de remplacement."))
        if vehicle == self.vehicle_id:
            raise UserError(_("Ce bus est déjà affecté à ce départ."))
        seats = vehicle.seats or 0
        if seats <= 0:
            raise UserError(_("Ce bus n'a pas de nombre de places."))
        numbers = []
        for booking in self._live_bookings():
            numbers.extend(booking.seat_ids.mapped('number'))
        missing = sorted({number for number in numbers if number > seats})
        if missing:
            raise UserError(_(
                "Ces sièges n'existent pas sur le bus de remplacement : %s. Reportez ces billets d'abord.",
                ', '.join(str(number) for number in missing),
            ))
        previous = self.vehicle_id.display_name or _("aucun")
        self.write({'vehicle_id': vehicle.id})
        self.message_post(body=_(
            "Bus remplacé : %s → %s (%s places).",
            previous,
            vehicle.display_name,
            seats,
        ))
        return True

    def action_open_delay(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Retard'),
            'res_model': 'transport.departure.delay',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_departure_id': self.id,
                'default_delay_minutes': self.delay_minutes,
                'default_reason': self.delay_reason,
            },
        }

    def action_open_swap(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Remplacer le bus'),
            'res_model': 'transport.departure.swap',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_departure_id': self.id},
        }

    @api.depends('departure_datetime', 'release_hours')
    def _compute_release_datetime(self):
        for departure in self:
            if departure.departure_datetime:
                departure.release_datetime = departure.departure_datetime - timedelta(
                    hours=departure.release_hours or 0,
                )
            else:
                departure.release_datetime = False

    @api.depends(
        'leg_ids',
        'booking_ids.state',
        'booking_ids.seat_count',
        'booking_ids.hold_until',
        'booking_ids.channel',
        'booking_ids.origin_sequence',
        'booking_ids.destination_sequence',
    )
    def _compute_seats_taken(self):
        for departure in self:
            taken = [leg.booked_seats() for leg in departure.leg_ids]
            departure.seats_taken = max(taken) if taken else 0

    @api.depends(
        'booking_ids.state',
        'booking_ids.seat_count',
        'booking_ids.paid',
        'booking_ids.amount_total',
        'booking_ids.refund_amount',
        'fuel_amount',
        'toll_amount',
        'driver_amount',
    )
    def _compute_result(self):
        sold_states = {'confirmed', 'boarded', 'noshow'}
        for departure in self:
            sold = 0
            collected = 0.0
            refunded = 0.0
            for booking in departure.booking_ids:
                if booking.state in sold_states:
                    sold += booking.seat_count
                if booking.paid:
                    collected += booking.amount_total
                refunded += booking.refund_amount or 0.0
            departure.seats_sold = sold
            departure.amount_collected = collected
            departure.amount_refunded = refunded
            departure.amount_net = collected - refunded
            departure.amount_cost = (
                (departure.fuel_amount or 0.0)
                + (departure.toll_amount or 0.0)
                + (departure.driver_amount or 0.0)
            )
            departure.amount_margin = departure.amount_net - departure.amount_cost

    @api.depends(
        'seat_capacity', 'line_id', 'line_id.seat_layout',
        'vehicle_id', 'vehicle_id.seat_layout', 'vehicle_id.model_id',
    )
    def _compute_seat_layout_label(self):
        for departure in self:
            plan = departure.seat_plan() if departure.seat_capacity else None
            departure.seat_layout_label = plan['title'] if plan else ''

    def _seat_layout_code(self):
        self.ensure_one()
        line_model = self.env['transport.line']
        vehicle_layout = self.vehicle_id.seat_layout
        if vehicle_layout and line_model.layout_fits(vehicle_layout, self.seat_capacity):
            return vehicle_layout
        if self.line_id.seat_layout and line_model.layout_fits(self.line_id.seat_layout, self.seat_capacity):
            return self.line_id.seat_layout
        return 'coach_2_2'

    def seat_plan(self, taken=None):
        self.ensure_one()
        if not self.seat_capacity:
            return None
        layout = self._seat_layout_code()
        plan = self.env['transport.line'].build_seat_plan(layout, self.seat_capacity, taken)
        vehicle = self.vehicle_id
        if vehicle and vehicle.seat_layout == layout and vehicle.model_id:
            plan['title'] = '%s · %s' % (vehicle.model_id.display_name, plan['label'])
        return plan

    @api.onchange('line_id')
    def _onchange_line(self):
        if not self.line_id:
            return
        self.seat_capacity = self.line_id.seat_capacity
        self.b2b_seat_reserve = self.line_id.b2b_seat_reserve
        self.release_hours = self.line_id.release_hours

    @api.onchange('vehicle_id')
    def _onchange_vehicle(self):
        if self.vehicle_id and self.vehicle_id.seats:
            self.seat_capacity = self.vehicle_id.seats

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        seen = set()
        for vals in vals_list:
            vals = dict(vals)
            line = self.env['transport.line'].browse(vals.get('line_id'))
            if not line:
                raise UserError(_("Choisissez une ligne."))
            departure_datetime = fields.Datetime.to_datetime(vals.get('departure_datetime'))
            if not departure_datetime:
                raise UserError(_("Choisissez la date et l'heure du départ."))
            vals['departure_datetime'] = departure_datetime
            slot = (line.id, departure_datetime)
            clash = slot in seen or self.search_count([
                ('line_id', '=', line.id),
                ('departure_datetime', '=', departure_datetime),
                ('state', '!=', 'cancelled'),
            ])
            if clash:
                raise UserError(_("Un départ existe déjà sur ce créneau."))
            seen.add(slot)
            vals.setdefault('seat_capacity', line.seat_capacity)
            vals.setdefault('b2b_seat_reserve', line.b2b_seat_reserve)
            vals.setdefault('release_hours', line.release_hours)
            if vals['b2b_seat_reserve'] > vals['seat_capacity']:
                raise UserError(_("La réserve entreprise doit tenir dans la capacité."))
            vals['company_id'] = line.company_id.id
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.departure') or _('Nouveau')
            vals['leg_ids'] = line._leg_commands(vals['seat_capacity'])
            prepared.append(vals)
        return super(TransportDeparture, self.with_context(transport_build_legs=True)).create(prepared)

    def write(self, vals):
        vals = dict(vals)
        if 'line_id' in vals:
            raise UserError(_("Le départ reste sur sa ligne."))
        if {'delay_minutes', 'delay_reason'} & set(vals):
            closed = self.filtered(lambda departure: departure.state in ('done', 'cancelled'))
            if closed:
                raise UserError(_("Ce départ n'accepte plus de retard."))
        if {'fuel_amount', 'toll_amount', 'driver_amount'} & set(vals):
            cancelled = self.filtered(lambda departure: departure.state == 'cancelled')
            if cancelled:
                raise UserError(_("Un départ annulé n'a pas de charges."))
        if vals.get('vehicle_id') and 'seat_capacity' not in vals:
            vehicle = self.env['fleet.vehicle'].browse(vals['vehicle_id'])
            if vehicle.seats:
                vals['seat_capacity'] = vehicle.seats
        frozen = self.filtered(lambda departure: departure.state in ('in_progress', 'done', 'cancelled'))
        frozen_fields = {
            'vehicle_id', 'driver_id', 'seat_capacity', 'b2b_seat_reserve',
            'release_hours', 'departure_datetime', 'schedule_id',
        }
        if frozen and frozen_fields & set(vals):
            raise UserError(_("Ce départ n'est plus modifiable."))
        if 'seat_capacity' in vals or 'b2b_seat_reserve' in vals:
            for departure in self:
                departure._assert_fits(
                    vals.get('seat_capacity', departure.seat_capacity),
                    vals.get('b2b_seat_reserve', departure.b2b_seat_reserve),
                )
        res = super().write(vals)
        if 'seat_capacity' in vals:
            for departure in self:
                departure.leg_ids.write({'seat_capacity': departure.seat_capacity})
        return res

    def unlink(self):
        for departure in self:
            if departure.state != 'planned':
                raise UserError(_("Seul un départ planifié se supprime. Annulez-le sinon."))
            if departure.booking_ids.filtered(lambda booking: booking.state != 'cancelled'):
                raise UserError(_("Ce départ a des réservations."))
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_("Régénérez le départ depuis l'horaire de la ligne."))

    def b2b_released(self, at=None):
        self.ensure_one()
        at = at or fields.Datetime.now()
        if not self.release_datetime:
            return True
        return at >= self.release_datetime

    def _assert_fits(self, capacity, reserve):
        self.ensure_one()
        if capacity <= 0:
            raise UserError(_("La capacité doit être positive."))
        if reserve > capacity or reserve < 0:
            raise UserError(_("La réserve entreprise doit tenir dans la capacité."))
        released = self.b2b_released()
        now = fields.Datetime.now()
        numbers = []
        for booking in self.booking_ids:
            if booking.state not in ('held', 'confirmed', 'boarded'):
                continue
            if booking.state == 'held' and (not booking.hold_until or booking.hold_until <= now):
                continue
            numbers.extend(booking.seat_ids.mapped('number'))
        too_high = sorted({number for number in numbers if number > capacity})
        if too_high:
            raise UserError(_(
                "Ces sièges dépassent la nouvelle capacité : %s.",
                ', '.join(str(number) for number in too_high),
            ))
        for leg in self.leg_ids:
            b2b = leg.booked_seats('b2b')
            b2c = leg.booked_seats('b2c')
            if b2b + b2c > capacity:
                raise UserError(_(
                    "Le tronçon %s → %s a déjà %s places prises pour une capacité de %s.",
                    leg.origin_stop_id.name,
                    leg.destination_stop_id.name,
                    b2b + b2c,
                    capacity,
                ))
            if not released and b2c + max(b2b, reserve) > capacity:
                raise UserError(_(
                    "La réserve entreprise ne laisse plus assez de places aux billets déjà pris sur %s → %s.",
                    leg.origin_stop_id.name,
                    leg.destination_stop_id.name,
                ))

    def _check_bookable(self):
        self.ensure_one()
        if self.state not in ('planned', 'assigned', 'boarding'):
            raise UserError(_("Ce départ n'accepte plus de réservations."))

    def _legs_between(self, origin, destination):
        self.ensure_one()
        stops = self.line_id.stop_ids.sorted('sequence')
        origin_line = stops.filtered(lambda stop: stop.stop_id == origin)[:1]
        destination_line = stops.filtered(lambda stop: stop.stop_id == destination)[:1]
        if not origin_line or not destination_line or origin_line.sequence >= destination_line.sequence:
            raise UserError(_("Le trajet doit partir d'un arrêt de la ligne et arriver plus loin."))
        if not origin_line.boarding:
            raise UserError(_("La montée est interdite à %s.", origin.display_name))
        if not destination_line.alighting:
            raise UserError(_("La descente est interdite à %s.", destination.display_name))
        legs = self.leg_ids.filtered(
            lambda leg: origin_line.sequence <= leg.from_sequence < destination_line.sequence,
        )
        if len(legs) != len(stops.filtered(
            lambda stop: origin_line.sequence <= stop.sequence < destination_line.sequence,
        )):
            raise UserError(_("Aucun tronçon ne couvre ce trajet."))
        return legs, origin_line.sequence, destination_line.sequence

    def book(self, origin, destination, seat_count, passenger_name, channel='b2c', partner=None, subscriber=None, seat_numbers=None, seat_names=None):
        self.ensure_one()
        vals = {
            'departure_id': self.id,
            'origin_stop_id': origin.id,
            'destination_stop_id': destination.id,
            'seat_count': seat_count,
            'passenger_name': passenger_name,
            'channel': channel,
        }
        if partner:
            vals['partner_id'] = partner.id
        if subscriber:
            vals['subscriber_id'] = subscriber.id
            vals['channel'] = 'b2b'
            if not passenger_name:
                vals['passenger_name'] = subscriber.name
        if seat_numbers:
            vals['seat_numbers'] = list(seat_numbers)
        if seat_names:
            vals['seat_names'] = list(seat_names)
        return self.env['transport.booking'].create(vals)

    def choose_seat_numbers(self, legs, seat_count, requested=None, reserved=None):
        """Pick seat numbers free on every leg of the trip."""
        self.ensure_one()
        now = fields.Datetime.now()
        taken = set()
        for booking in self.booking_ids:
            if any(booking._occupies_leg(leg, now) for leg in legs):
                taken.update(booking.seat_ids.mapped('number'))
        for departure, other_legs, numbers in reserved or []:
            if departure == self and (other_legs & legs):
                taken.update(numbers)
        if requested:
            numbers = []
            for item in requested:
                try:
                    number = int(item)
                except (TypeError, ValueError):
                    number = 0
                numbers.append(number)
            if len(numbers) != seat_count or len(set(numbers)) != len(numbers):
                raise UserError(_("Cochez exactement %s siège(s) distinct(s).", seat_count))
            if any(number < 1 or number > self.seat_capacity for number in numbers):
                raise UserError(_("Ce siège n'existe pas sur ce car."))
            clash = [str(number) for number in numbers if number in taken]
            if clash:
                raise UserError(_("Siège déjà pris sur ce trajet : %s.", ', '.join(clash)))
            return numbers
        free = [number for number in range(1, self.seat_capacity + 1) if number not in taken]
        if len(free) < seat_count:
            raise UserError(_("Plus assez de sièges libres sur ce trajet."))
        return free[:seat_count]

    def has_left(self, at=None):
        """True once the real departure time, delay included, is reached."""
        self.ensure_one()
        at = at or fields.Datetime.now()
        moment = self.effective_datetime or self.departure_datetime
        return bool(moment and moment <= at)

    def _service_date(self):
        self.ensure_one()
        moment = self.effective_datetime or self.departure_datetime
        if not moment:
            return False
        return self._local_time(moment).date()

    def _missing_documents(self, driver):
        self.ensure_one()
        day = self._service_date()
        documents = self.env['transport.driver.document'].search([
            ('employee_id', '=', driver.id),
            ('expires_on', '>=', day),
        ])
        present = set(documents.mapped('doc_type'))
        return [label for key, label in DOCUMENT_TYPES if key not in present]

    def _assert_driver_fit(self):
        for departure in self:
            missing = departure._missing_documents(departure.driver_id)
            if missing:
                raise UserError(_(
                    "Habilitations manquantes ou expirées pour %s : %s.",
                    departure.driver_id.name,
                    ", ".join(missing),
                ))

    def _ensure_checks(self):
        templates = self.env['transport.check.template'].search([])
        if not templates:
            raise UserError(_("Aucun point de contrôle n'est configuré."))
        for departure in self:
            existing = set(departure.check_ids.mapped('template_id').ids)
            missing = templates.filtered(lambda template: template.id not in existing)
            if missing:
                self.env['transport.departure.check'].create([
                    {'departure_id': departure.id, 'template_id': template.id}
                    for template in missing
                ])
                departure.invalidate_recordset(['check_ids'])

    def _assert_checks(self):
        for departure in self:
            blocked = departure.check_ids.filtered(
                lambda check: check.critical and check.result != 'ok',
            )
            if not departure.check_ids or blocked:
                names = ", ".join(blocked.mapped('name')) or _("checklist absente")
                raise UserError(_("Départ bloqué. Contrôle critique non conforme : %s.", names))

    def _require_state(self, expected):
        if any(departure.state != expected for departure in self):
            raise UserError(_("Cette action n'est pas disponible sur ce statut."))

    def _check_crew(self):
        for departure in self:
            if not departure.vehicle_id or not departure.driver_id:
                raise UserError(_("Choisissez un bus et un chauffeur."))
            seats = departure.vehicle_id.seats or 0
            if seats <= 0:
                raise UserError(_("Ce bus n'a pas de nombre de places."))
            if departure.seat_capacity > seats:
                raise UserError(_("La capacité dépasse le nombre de sièges du bus."))
            departure._assert_driver_fit()

    def action_assign(self):
        self._require_state('planned')
        self._check_crew()
        self.write({'state': 'assigned'})
        return True

    def _trip_window(self):
        self.ensure_one()
        start = self.effective_datetime or self.departure_datetime
        hours = self.line_id.drive_hours or 0.0
        return start, start + timedelta(hours=hours) if start else (False, False)

    def _windows_overlap(self, start, end, other):
        other_start, other_end = other._trip_window()
        if not start or not end or not other_start or not other_end:
            return False
        return start < other_end and other_start < end

    def _crew_busy(self, driver=None, vehicle=None, start=None, end=None):
        self.ensure_one()
        domain = [('state', '!=', 'cancelled'), ('id', '!=', self.id)]
        if driver:
            domain.append(('driver_id', '=', driver.id))
        if vehicle:
            domain.append(('vehicle_id', '=', vehicle.id))
        for other in self.search(domain):
            if self._windows_overlap(start, end, other):
                return other
        return self.browse()

    def _driver_hours(self, driver):
        self.ensure_one()
        others = self.search([
            ('driver_id', '=', driver.id),
            ('state', '!=', 'cancelled'),
            ('id', '!=', self.id),
            ('service_date', '=', self.service_date),
        ])
        return sum(other.line_id.drive_hours or 0.0 for other in others)

    def _same_trip_count(self, driver):
        """How often this driver already drove this schedule, yesterday and over 7 days."""
        self.ensure_one()
        if not self.service_date:
            return 0, 0
        domain = [
            ('driver_id', '=', driver.id),
            ('line_id', '=', self.line_id.id),
            ('state', '!=', 'cancelled'),
            ('id', '!=', self.id),
            ('service_date', '>=', self.service_date - timedelta(days=7)),
            ('service_date', '<', self.service_date),
        ]
        if self.schedule_id:
            domain.append(('schedule_id', '=', self.schedule_id.id))
        past = self.search(domain)
        yesterday = self.service_date - timedelta(days=1)
        did_yesterday = 1 if any(item.service_date == yesterday for item in past) else 0
        return did_yesterday, len(past)

    def _pick_bus(self):
        self.ensure_one()
        line = self.line_id
        if not line.distance_km:
            raise UserError(_("Indiquez la distance des arrêts avant d'affecter automatiquement."))
        size = LENGTH_TO_SIZE[line.route_length]
        size_label = dict(BUS_SIZES)[size]
        length_label = dict(ROUTE_LENGTHS)[line.route_length]
        needed = self.seat_capacity
        vehicles = self.env['fleet.vehicle'].search([
            ('bus_size', '=', size),
            ('seats', '>=', needed),
            ('company_id', 'in', [False, self.company_id.id]),
        ])
        start, end = self._trip_window()
        free = vehicles.filtered(lambda vehicle: not self._crew_busy(vehicle=vehicle, start=start, end=end))
        if not free:
            raise UserError(_(
                "Trajet %s, %s km, %s : aucun bus %s d'au moins %s places n'est libre.",
                line.display_name,
                int(line.distance_km),
                length_label,
                size_label,
                needed,
            ))
        return free.sorted(lambda vehicle: (vehicle.seats, vehicle.id))[:1]

    def _driver_block_reason(self, driver, hours, start, end):
        self.ensure_one()
        if driver.company_id and driver.company_id != self.company_id:
            return _("autre société")
        missing = self._missing_documents(driver)
        if missing:
            return _("habilitations : %s", ", ".join(missing))
        busy = self._crew_busy(driver=driver, start=start, end=end)
        if busy:
            return _("déjà au volant sur %s", busy.name)
        used = self._driver_hours(driver)
        if used + hours > MAX_DRIVE_HOURS + 1e-6:
            return _("%.1f h déjà conduites, ce trajet en ajoute %.1f h, maximum %s h", used, hours, MAX_DRIVE_HOURS)
        return False

    def _pick_driver(self):
        self.ensure_one()
        line = self.line_id
        hours = line.drive_hours or 0.0
        if hours > MAX_DRIVE_HOURS + 1e-6:
            raise UserError(_(
                "Ce trajet demande %.1f h de conduite. Le maximum d'un chauffeur est %s h par jour.",
                hours,
                MAX_DRIVE_HOURS,
            ))
        routes = self.env['transport.driver.route'].search([('line_id', '=', line.id)])
        if not routes:
            raise UserError(_("Aucun chauffeur n'est affecté à l'itinéraire %s.", line.display_name))
        start, end = self._trip_window()
        ranked = []
        rejected = []
        for route in routes:
            driver = route.employee_id
            reason = self._driver_block_reason(driver, hours, start, end)
            if reason:
                rejected.append("%s : %s" % (driver.name, reason))
                continue
            yesterday, recent = self._same_trip_count(driver)
            ranked.append((yesterday, recent, self._driver_hours(driver), driver.id, driver))
        if not ranked:
            raise UserError(_(
                "Aucun chauffeur de %s ne peut prendre ce départ.\n%s",
                line.display_name,
                "\n".join(rejected),
            ))
        ranked.sort()
        return ranked[0][4]

    def action_auto_assign(self):
        """Pick a bus from the route length and a driver of that line."""
        if not self:
            raise UserError(_("Sélectionnez des départs planifiés."))
        blocked = self.filtered(lambda departure: departure.state != 'planned')
        if blocked:
            raise UserError(_("Seuls les départs planifiés s'affectent automatiquement."))
        ordered = self.sorted(lambda departure: (
            departure.service_date or fields.Date.from_string('1970-01-01'),
            departure.effective_datetime or departure.departure_datetime,
            departure.id,
        ))
        for departure in ordered:
            vehicle = departure._pick_bus()
            driver = departure._pick_driver()
            used = departure._driver_hours(driver)
            departure.write({
                'vehicle_id': vehicle.id,
                'driver_id': driver.id,
                'seat_capacity': departure.seat_capacity,
            })
            departure.action_assign()
            size_label = dict(BUS_SIZES).get(vehicle.bus_size, '')
            departure.message_post(body=_(
                "Affectation automatique : bus %s (%s, %s places), chauffeur %s. "
                "Conduite de ce trajet : %.1f h. Déjà %.1f h ce jour pour ce chauffeur.",
                vehicle.display_name,
                size_label,
                vehicle.seats,
                driver.name,
                departure.line_id.drive_hours,
                used,
            ))
        return True

    def action_open_boarding(self):
        self._require_state('assigned')
        self._check_crew()
        self._ensure_checks()
        self.write({'state': 'boarding'})
        return True

    def action_start(self):
        self._require_state('boarding')
        self._check_crew()
        self._ensure_checks()
        self._assert_checks()
        self.write({'state': 'in_progress'})
        return True

    def action_done(self):
        self._require_state('in_progress')
        self.write({'state': 'done'})
        return True

    def action_cancel(self):
        for departure in self:
            if departure.state in ('in_progress', 'done', 'cancelled'):
                raise UserError(_("Ce départ ne peut plus être annulé."))
            if departure.booking_ids.filtered(lambda booking: booking.state in ('confirmed', 'boarded')):
                raise UserError(_("Annulez les réservations confirmées avant d'annuler le départ."))
        holds = self.booking_ids.filtered(lambda booking: booking.state == 'held')
        if holds:
            holds.with_context(transport_skip_waitlist_offer=True).action_cancel()
        waiting = self.waitlist_ids.filtered(lambda entry: entry.state in ('waiting', 'offered'))
        if waiting:
            waiting.write({'state': 'cancelled'})
        self.write({'state': 'cancelled'})
        return True

    @api.model
    def close_service_day(self, day, reason, line=None):
        """Cancel open departures of one local day. A bus already running stays on the road."""
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_("Indiquez le motif de la fermeture."))
        day = fields.Date.to_date(day)
        if not day:
            raise UserError(_("Choisissez le jour."))
        domain = [('state', 'in', ('planned', 'assigned', 'boarding'))]
        if line:
            domain.append(('line_id', '=', line.id))
        chosen = self.search(domain).filtered(lambda departure: departure._service_date() == day)
        closed = self.browse()
        kept = self.browse()
        for departure in chosen:
            if departure.booking_ids.filtered(lambda booking: booking.state == 'boarded'):
                kept |= departure
                continue
            departure.booking_ids.filtered(
                lambda booking: booking.state in ('held', 'confirmed'),
            ).with_context(transport_closure_reason=reason).cancel_for_closure()
            waiting = departure.waitlist_ids.filtered(
                lambda entry: entry.state in ('waiting', 'offered'),
            )
            if waiting:
                waiting.write({'state': 'cancelled'})
            departure.action_cancel()
            departure.message_post(body=_("Journée fermée : %s", reason))
            closed |= departure
        return closed, kept

    def _manifest_bookings(self):
        self.ensure_one()
        return self.booking_ids.filtered(
            lambda booking: booking.state in ('confirmed', 'boarded', 'noshow'),
        )

    def manifest_rows(self):
        self.ensure_one()
        rows = []
        for booking in self._manifest_bookings():
            seats = booking.seat_ids.sorted('number')
            if not seats:
                rows.append({
                    'seat': '',
                    'name': booking.passenger_name,
                    'channel': booking.channel,
                    'origin': booking.origin_stop_id.name,
                    'destination': booking.destination_stop_id.name,
                    'state': booking.state,
                })
                continue
            for seat in seats:
                rows.append({
                    'seat': seat.number,
                    'name': seat.passenger_name or booking.passenger_name,
                    'channel': booking.channel,
                    'origin': booking.origin_stop_id.name,
                    'destination': booking.destination_stop_id.name,
                    'state': booking.state,
                })
        return rows

    def scan_path(self):
        self.ensure_one()
        return '/embarquer/%s?db=%s' % (self.id, self.env.cr.dbname)

    def action_open_scan(self):
        self.ensure_one()
        if self.state not in ('boarding', 'in_progress'):
            raise UserError(_("Le scan est ouvert pendant l'embarquement et la course."))
        return {
            'type': 'ir.actions.act_url',
            'url': self.scan_path(),
            'target': 'new',
        }
