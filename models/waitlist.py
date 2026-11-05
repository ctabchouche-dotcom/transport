# -*- coding: utf-8 -*-
import hashlib
import hmac
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TransportWaitlist(models.Model):
    _name = 'transport.waitlist'
    _description = 'Liste d\'attente'
    _order = 'id'

    name = fields.Char(string='Référence', required=True, copy=False, default='/')
    departure_id = fields.Many2one(
        'transport.departure', string='Départ', required=True, ondelete='cascade', index=True,
    )
    origin_stop_id = fields.Many2one('transport.stop', string='Montée', required=True, ondelete='restrict')
    destination_stop_id = fields.Many2one('transport.stop', string='Descente', required=True, ondelete='restrict')
    passenger_name = fields.Char(string='Passager', required=True)
    phone = fields.Char(string='Téléphone', required=True)
    email = fields.Char(string='E-mail')
    seat_count = fields.Integer(string='Places', required=True, default=1)
    state = fields.Selection(
        [
            ('waiting', 'En attente'),
            ('offered', 'Place proposée'),
            ('booked', 'Place prise'),
            ('expired', 'Délai dépassé'),
            ('cancelled', 'Annulée'),
        ],
        string='Statut',
        default='waiting',
        required=True,
        index=True,
    )
    offer_until = fields.Datetime(string='À prendre avant')
    booking_id = fields.Many2one('transport.booking', string='Réservation', ondelete='set null')

    _seat_count_positive = models.Constraint(
        'CHECK(seat_count > 0)',
        'Le nombre de places doit être positif.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.waitlist') or _('Nouveau')
        return super().create(vals_list)

    def access_token(self):
        self.ensure_one()
        digest = hmac.new(
            self.env['transport.ticket']._secret().encode(),
            f'wait:{self.id}:{self.name}'.encode(),
            hashlib.sha256,
        ).hexdigest()[:24]
        return digest

    def claim_url(self):
        self.ensure_one()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        return '%s/reserver-un-billet/attente/%s/%s?db=%s' % (
            base.rstrip('/'), self.id, self.access_token(), self.env.cr.dbname,
        )

    def _room_for(self):
        self.ensure_one()
        legs, _origin_sequence, _destination_sequence = self.departure_id._legs_between(
            self.origin_stop_id, self.destination_stop_id,
        )
        free = min(leg.free_seats('b2c') for leg in legs) if legs else 0
        return free >= self.seat_count

    @api.model
    def join_public(self, departure_id, origin_id, destination_id, passenger_name, phone, email=None, seat_count=1):
        departure = self.env['transport.departure'].browse(departure_id).exists()
        if not departure or departure.line_id.line_type == 'b2b':
            raise UserError(_("Choisissez un départ."))
        if departure.state not in ('planned', 'assigned', 'boarding'):
            raise UserError(_("Ce départ n'accepte plus de réservations."))
        if not departure.departure_datetime or departure.has_left():
            raise UserError(_("Ce départ est déjà parti."))
        name = (passenger_name or '').strip()
        phone = (phone or '').strip()
        if len(name) < 2:
            raise UserError(_("Indiquez votre nom."))
        if len(phone) < 6:
            raise UserError(_("Indiquez un téléphone où le guichet peut vous joindre."))
        try:
            seat_count = int(seat_count)
        except (TypeError, ValueError):
            seat_count = 0
        if seat_count < 1 or seat_count > 8:
            raise UserError(_("Le nombre de places doit être entre 1 et 8."))
        origin = self.env['transport.stop'].browse(origin_id).exists()
        destination = self.env['transport.stop'].browse(destination_id).exists()
        if departure.b2c_free_between(origin, destination) >= seat_count:
            raise UserError(_("Il reste des places. Réservez le billet."))
        key = self.env['transport.booking']._phone_key(phone)
        already = self.search([
            ('departure_id', '=', departure.id),
            ('state', 'in', ('waiting', 'offered')),
        ])
        for entry in already:
            if self.env['transport.booking']._phone_key(entry.phone) != key:
                continue
            if entry.state == 'waiting':
                entry.write({
                    'origin_stop_id': origin.id,
                    'destination_stop_id': destination.id,
                    'passenger_name': name[:128],
                    'seat_count': seat_count,
                    'email': (email or '').strip()[:128] or entry.email,
                })
            return entry
        return self.create({
            'departure_id': departure.id,
            'origin_stop_id': origin.id,
            'destination_stop_id': destination.id,
            'passenger_name': name[:128],
            'phone': phone[:32],
            'email': (email or '').strip()[:128] or False,
            'seat_count': seat_count,
        })

    def _notify_offer(self):
        template = self.env.ref('transport.email_template_waitlist', raise_if_not_found=False)
        for entry in self:
            if template and entry.email:
                template.send_mail(entry.id, force_send=False)

    def _expire_late_offers(self):
        now = fields.Datetime.now()
        late = self.filtered(lambda entry: entry.state == 'offered' and entry.offer_until and entry.offer_until <= now)
        if late:
            late.write({'state': 'expired'})

    @api.model
    def offer_open(self, departures):
        """Propose the next waiting passenger when a seat is free for the public."""
        if not departures:
            return False
        minutes = self.env['transport.booking']._hold_minutes()
        now = fields.Datetime.now()
        for departure in departures:
            if departure.state not in ('planned', 'assigned', 'boarding') or departure.has_left():
                continue
            queue = self.search([
                ('departure_id', '=', departure.id),
                ('state', 'in', ('waiting', 'offered')),
            ], order='id')
            queue._expire_late_offers()
            if queue.filtered(lambda entry: entry.state == 'offered'):
                continue
            for entry in queue.filtered(lambda item: item.state == 'waiting'):
                if not entry._room_for():
                    continue
                entry.write({
                    'state': 'offered',
                    'offer_until': now + timedelta(minutes=minutes),
                })
                entry._notify_offer()
                break
        return True

    def claim(self):
        self.ensure_one()
        self._expire_late_offers()
        if self.state != 'offered':
            raise UserError(_("Cette place n'est plus proposée."))
        if not self._room_for():
            self.write({'state': 'waiting', 'offer_until': False})
            raise UserError(_("La place vient d'être prise. Vous restez en liste d'attente."))
        booking = self.env['transport.booking'].book_public(
            self.departure_id.id,
            self.origin_stop_id.id,
            self.destination_stop_id.id,
            self.passenger_name,
            self.phone,
            email=self.email,
            seat_count=self.seat_count,
        )
        self.write({'state': 'booked', 'booking_id': booking.id})
        return booking

    @api.model
    def find_public(self, reference, phone):
        reference = (reference or '').strip()
        key = self.env['transport.booking']._phone_key(phone)
        if len(reference) < 2 or len(key) < 6:
            raise UserError(_("Indiquez la référence du billet et le téléphone."))
        entry = self.sudo().search([('name', '=ilike', reference)], limit=1)
        if not entry or self.env['transport.booking']._phone_key(entry.phone) != key:
            raise UserError(_("Billet introuvable."))
        return entry
