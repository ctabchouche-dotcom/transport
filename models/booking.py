# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import timedelta
import hashlib
import hmac

from odoo import api, fields, models, _
from odoo.exceptions import UserError

PROTECTED_FIELDS = {
    'departure_id', 'origin_stop_id', 'destination_stop_id', 'channel',
    'seat_count', 'origin_sequence', 'destination_sequence', 'hold_until', 'name',
    'subscriber_id',
}


class TransportBooking(models.Model):
    _name = 'transport.booking'
    _description = 'Réservation'
    _order = 'id desc'

    name = fields.Char(string='Référence', required=True, copy=False, default='/', readonly=True)
    departure_id = fields.Many2one(
        'transport.departure', string='Départ', required=True, ondelete='restrict', index=True,
    )
    origin_stop_id = fields.Many2one('transport.stop', string='Montée', required=True, ondelete='restrict')
    destination_stop_id = fields.Many2one('transport.stop', string='Descente', required=True, ondelete='restrict')
    origin_sequence = fields.Integer(required=True, readonly=True)
    destination_sequence = fields.Integer(required=True, readonly=True)
    channel = fields.Selection(
        [
            ('b2c', 'Billet individuel'),
            ('b2b', 'Abonné entreprise'),
        ],
        string='Canal',
        required=True,
        default='b2c',
        index=True,
    )
    seat_count = fields.Integer(string='Places', required=True, default=1)
    passenger_name = fields.Char(string='Passager', required=True)
    phone = fields.Char(string='Téléphone')
    partner_id = fields.Many2one('res.partner', string='Contact')
    subscriber_id = fields.Many2one(
        'transport.subscriber', string='Abonné', ondelete='restrict', index=True,
    )
    line_id = fields.Many2one(related='departure_id.line_id')
    ticket_ids = fields.One2many('transport.ticket', 'booking_id', string='Billets')
    ticket_id = fields.Many2one('transport.ticket', compute='_compute_ticket_id')
    seat_ids = fields.One2many('transport.booking.seat', 'booking_id', string='Numéros')
    seat_label = fields.Char(string='Sièges', compute='_compute_seat_label')
    seat_detail = fields.Char(string='Sièges et noms', compute='_compute_seat_label')
    state = fields.Selection(
        [
            ('held', 'En attente'),
            ('confirmed', 'Confirmée'),
            ('boarded', 'Embarquée'),
            ('noshow', 'No-show'),
            ('cancelled', 'Annulée'),
        ],
        string='Statut',
        default='held',
        required=True,
        index=True,
    )
    hold_until = fields.Datetime(string='Tenue jusqu\'au', index=True, readonly=True)
    fare_unit = fields.Float(string='Prix unitaire', readonly=True)
    amount_total = fields.Float(string='Montant', readonly=True)
    paid = fields.Boolean(string='Payé', readonly=True)
    payment_method = fields.Selection(
        [
            ('online', 'En ligne'),
            ('cash', 'Espèces'),
            ('tpe', 'TPE'),
        ],
        string='Mode de paiement',
        readonly=True,
    )
    payment_reference = fields.Char(string='Reçu', readonly=True)
    refund_amount = fields.Float(string='Remboursement', readonly=True)
    closure_reason = fields.Char(string='Motif de fermeture', readonly=True)
    allowed_stop_ids = fields.Many2many(
        'transport.stop', compute='_compute_allowed_stop_ids', string='Arrêts de la ligne',
    )

    _seat_count_positive = models.Constraint(
        'CHECK(seat_count > 0)',
        'Le nombre de places doit être positif.',
    )

    @api.depends('ticket_ids')
    def _compute_ticket_id(self):
        for booking in self:
            booking.ticket_id = booking.ticket_ids[:1]

    @api.depends('seat_ids.number', 'seat_ids.passenger_name', 'passenger_name')
    def _compute_seat_label(self):
        for booking in self:
            seats = booking.seat_ids.sorted('number')
            booking.seat_label = ', '.join(str(seat.number) for seat in seats)
            booking.seat_detail = ', '.join(
                '%s %s' % (seat.number, seat.passenger_name or booking.passenger_name or '')
                for seat in seats
            )

    def _names_for_seats(self, count, names):
        self.ensure_one()
        provided = [(name or '').strip()[:128] for name in (names or [])]
        lead = (self.passenger_name or '').strip()[:128] or _('Passager')
        result = []
        for index in range(count):
            if index < len(provided) and provided[index]:
                result.append(provided[index])
            elif index == 0:
                result.append(lead)
            else:
                result.append(_('Passager %s', index + 1))
        return result

    @api.depends('departure_id.line_id.stop_ids.stop_id')
    def _compute_allowed_stop_ids(self):
        for booking in self:
            booking.allowed_stop_ids = booking.departure_id.line_id.stop_ids.stop_id

    @api.onchange('departure_id')
    def _onchange_departure(self):
        stops = self.departure_id.line_id.stop_ids.stop_id
        if self.origin_stop_id and self.origin_stop_id not in stops:
            self.origin_stop_id = False
        if self.destination_stop_id and self.destination_stop_id not in stops:
            self.destination_stop_id = False

    @api.model
    def _hold_minutes(self):
        raw = self.env['ir.config_parameter'].sudo().get_param('transport.hold_minutes', '15')
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            minutes = 15
        return minutes if minutes > 0 else 15

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        legs = self.env['transport.leg']
        for vals in vals_list:
            clean, taken = self._prepare_vals(vals)
            prepared.append((clean, taken))
            legs |= taken
        legs._lock()
        extra = defaultdict(lambda: {'b2b': 0, 'b2c': 0})
        extra_contract = defaultdict(int)
        cleaned = []
        number_plan = []
        name_plan = []
        reserved = []
        for vals, taken in prepared:
            requested = vals.pop('seat_numbers', None)
            seat_names = vals.pop('seat_names', None)
            self._check_free(taken, vals['channel'], vals['seat_count'], extra)
            if vals['channel'] == 'b2b':
                subscriber = self.env['transport.subscriber'].browse(vals['subscriber_id'])
                contract = subscriber.contract_id
                departure = self.env['transport.departure'].browse(vals['departure_id'])
                used = contract.seats_on(departure) + extra_contract[contract.id]
                if used + vals['seat_count'] > contract.seat_quota:
                    raise UserError(_(
                        "Le quota du contrat %s est atteint sur ce départ.",
                        contract.name,
                    ))
                extra_contract[contract.id] += vals['seat_count']
            for leg in taken:
                extra[leg.id][vals['channel']] += vals['seat_count']
            departure = self.env['transport.departure'].browse(vals['departure_id'])
            numbers = departure.choose_seat_numbers(
                taken, vals['seat_count'], requested, reserved,
            )
            reserved.append((departure, taken, numbers))
            number_plan.append(numbers)
            name_plan.append(seat_names)
            cleaned.append(vals)
        records = super().create(cleaned)
        seats = self.env['transport.booking.seat']
        for booking, numbers, seat_names in zip(records, number_plan, name_plan):
            labels = booking._names_for_seats(len(numbers), seat_names)
            seats.create([
                {
                    'booking_id': booking.id,
                    'number': number,
                    'passenger_name': label,
                }
                for number, label in zip(numbers, labels)
            ])
        return records

    def write(self, vals):
        if 'state' in vals and not self.env.context.get('transport_booking_state'):
            raise UserError(_("Utilisez les boutons Confirmer ou Annuler."))
        if PROTECTED_FIELDS & set(vals):
            allowed = set()
            if self.env.context.get('transport_extend_hold'):
                allowed.add('hold_until')
            if self.env.context.get('transport_rebook'):
                allowed.update({'departure_id', 'origin_sequence', 'destination_sequence'})
            if (PROTECTED_FIELDS - allowed) & set(vals):
                raise UserError(_("Une réservation ne se modifie pas. Annulez-la et recréez-la."))
        return super().write(vals)

    def copy(self, default=None):
        raise UserError(_("Créez une nouvelle réservation."))

    @api.model
    def _prepare_vals(self, vals):
        vals = dict(vals)
        departure = self.env['transport.departure'].browse(vals.get('departure_id'))
        if not departure:
            raise UserError(_("Choisissez un départ."))
        departure._check_bookable()
        origin = self.env['transport.stop'].browse(vals.get('origin_stop_id'))
        destination = self.env['transport.stop'].browse(vals.get('destination_stop_id'))
        if not origin or not destination:
            raise UserError(_("Choisissez l'arrêt de montée et l'arrêt de descente."))
        seat_count = vals.get('seat_count') or 0
        if seat_count <= 0:
            raise UserError(_("Le nombre de places doit être positif."))
        channel = vals.get('channel') or 'b2c'
        if channel not in ('b2c', 'b2b'):
            raise UserError(_("Canal de vente inconnu."))
        if channel == 'b2c' and vals.get('subscriber_id'):
            raise UserError(_("Un billet individuel n'est pas rattaché à un abonné."))
        if channel == 'b2b':
            self._assert_subscriber(departure, vals.get('subscriber_id'))
        if not vals.get('passenger_name') and vals.get('subscriber_id'):
            subscriber = self.env['transport.subscriber'].browse(vals['subscriber_id'])
            vals['passenger_name'] = subscriber.name
        if not vals.get('passenger_name') and vals.get('partner_id'):
            vals['passenger_name'] = self.env['res.partner'].browse(vals['partner_id']).name
        if not vals.get('passenger_name'):
            raise UserError(_("Indiquez le passager."))
        taken, origin_sequence, destination_sequence = departure._legs_between(origin, destination)
        if not vals.get('name') or vals.get('name') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('transport.booking') or _('Nouveau')
        vals.update({
            'channel': channel,
            'seat_count': seat_count,
            'state': 'held',
            'origin_sequence': origin_sequence,
            'destination_sequence': destination_sequence,
            'hold_until': fields.Datetime.now() + timedelta(minutes=self._hold_minutes()),
        })
        return vals, taken

    @api.model
    def _assert_subscriber(self, departure, subscriber_id):
        subscriber = self.env['transport.subscriber'].browse(subscriber_id).exists()
        if not subscriber:
            raise UserError(_("Un abonné entreprise est obligatoire."))
        if not subscriber.covers(departure.line_id, departure._service_date()):
            raise UserError(_("Cet abonné n'est pas couvert pour cette ligne à cette date."))
        return subscriber

    @api.model
    def _check_free(self, legs, channel, seat_count, extra):
        label = _("la vente individuelle") if channel == 'b2c' else _("l'entreprise")
        for leg in legs:
            free = leg.free_seats(
                channel,
                extra_b2b=extra[leg.id]['b2b'],
                extra_b2c=extra[leg.id]['b2c'],
            )
            if seat_count > free:
                raise UserError(_(
                    "Plus assez de places sur %s → %s : %s demandée(s), %s libre(s) pour %s.",
                    leg.origin_stop_id.name,
                    leg.destination_stop_id.name,
                    seat_count,
                    max(free, 0),
                    label,
                ))

    def _occupies_leg(self, leg, at):
        self.ensure_one()
        if self.departure_id != leg.departure_id:
            return False
        if self.state not in ('held', 'confirmed', 'boarded'):
            return False
        if self.state == 'held' and (not self.hold_until or self.hold_until <= at):
            return False
        return self.origin_sequence <= leg.from_sequence < self.destination_sequence

    def _covered_legs(self):
        self.ensure_one()
        return self.departure_id.leg_ids.filtered(
            lambda leg: self.origin_sequence <= leg.from_sequence < self.destination_sequence,
        )

    def action_confirm(self):
        now = fields.Datetime.now()
        legs = self.env['transport.leg']
        for booking in self:
            legs |= booking._covered_legs()
        legs._lock()
        for booking in self:
            if booking.state != 'held':
                raise UserError(_("Seule une réservation en attente peut être confirmée."))
            if not booking.hold_until or booking.hold_until <= now:
                raise UserError(_("Le délai de tenue est dépassé. Reprenez la réservation."))
            if booking.channel == 'b2b':
                self._assert_subscriber(booking.departure_id, booking.subscriber_id.id)
            booking.departure_id._check_bookable()
        self.with_context(transport_booking_state=True).write({'state': 'confirmed'})
        self.env['transport.ticket'].issue(self)
        return True

    def action_board(self):
        for booking in self:
            if booking.state != 'confirmed':
                raise UserError(_("Seul un billet confirmé s'embarque."))
            if booking.channel == 'b2c' and not booking.paid:
                raise UserError(_("Ce billet individuel n'est pas payé."))
            if booking.departure_id.state not in ('boarding', 'in_progress'):
                raise UserError(_("L'embarquement n'est pas ouvert sur ce départ."))
            if not booking.ticket_id:
                raise UserError(_("Ce billet n'a pas été émis."))
        self.with_context(transport_booking_state=True).write({'state': 'boarded'})
        self.ticket_ids.write({'state': 'boarded'})
        return True

    def action_noshow(self):
        for booking in self:
            if booking.state != 'confirmed':
                raise UserError(_("Seul un passager confirmé peut être noté absent."))
            if booking.departure_id.state not in ('boarding', 'in_progress'):
                raise UserError(_("L'absence se note pendant l'embarquement ou la course."))
        self.with_context(transport_booking_state=True).write({'state': 'noshow'})
        self.ticket_ids.write({'state': 'noshow'})
        return True

    def within_cancel_window(self):
        self.ensure_one()
        moment = self.departure_id.effective_datetime or self.departure_id.departure_datetime
        if not moment:
            return False
        deadline = moment - timedelta(hours=self.line_id.cancel_hours or 0)
        return fields.Datetime.now() < deadline

    def cancel_rule_label(self):
        self.ensure_one()
        return _(
            "Annulation jusqu'à %s h avant le départ : remboursement %s %%.",
            self.line_id.cancel_hours or 0,
            self.line_id.refund_percent or 0,
        )

    def _refund_due(self):
        self.ensure_one()
        if not self.paid or not self.within_cancel_window():
            return 0.0
        rate = self.line_id.refund_percent or 0
        return self.amount_total * rate / 100.0

    def action_open_rebook(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reporter le billet'),
            'res_model': 'transport.booking.rebook',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_booking_id': self.id},
        }

    def action_rebook(self, target):
        """Move the ticket onto another departure of the same line. The price stays."""
        target.ensure_one()
        if target.has_left():
            raise UserError(_("Ce départ est déjà parti."))
        target._check_bookable()
        for booking in self:
            if booking.state not in ('held', 'confirmed'):
                raise UserError(_("Seule une réservation en attente ou confirmée se reporte."))
            if booking.departure_id.state in ('in_progress', 'done', 'cancelled'):
                raise UserError(_("Le départ est déjà en course."))
            if target.line_id != booking.line_id:
                raise UserError(_("Le report reste sur la même ligne."))
            if target == booking.departure_id:
                raise UserError(_("Choisissez un autre départ."))
            if booking.channel == 'b2b':
                subscriber = booking.subscriber_id
                if not subscriber.covers(target.line_id, target._service_date()):
                    raise UserError(_("Cet abonné n'est pas couvert à la date du nouveau départ."))
                if subscriber.contract_id.seats_on(target) + booking.seat_count > subscriber.contract_id.seat_quota:
                    raise UserError(_(
                        "Le quota du contrat %s est atteint sur ce départ.",
                        subscriber.contract_id.name,
                    ))
            legs, origin_sequence, destination_sequence = target._legs_between(
                booking.origin_stop_id, booking.destination_stop_id,
            )
            legs._lock()
            self._check_free(legs, booking.channel, booking.seat_count, defaultdict(lambda: {'b2b': 0, 'b2c': 0}))
            wanted = booking.seat_ids.sorted('number')
            wanted_numbers = wanted.mapped('number')
            wanted_names = wanted.mapped('passenger_name')
            try:
                numbers = target.choose_seat_numbers(legs, booking.seat_count, wanted_numbers or None)
            except UserError:
                numbers = target.choose_seat_numbers(legs, booking.seat_count, None)
            source = booking.departure_id
            booking.with_context(transport_rebook=True).write({
                'departure_id': target.id,
                'origin_sequence': origin_sequence,
                'destination_sequence': destination_sequence,
            })
            booking.seat_ids.unlink()
            labels = booking._names_for_seats(len(numbers), wanted_names)
            self.env['transport.booking.seat'].create([
                {
                    'booking_id': booking.id,
                    'number': number,
                    'passenger_name': label,
                }
                for number, label in zip(numbers, labels)
            ])
            note = _(
                "Billet %s reporté : %s → %s. Sièges : %s.",
                booking.name,
                source.name,
                target.name,
                ', '.join(str(number) for number in numbers),
            )
            source.message_post(body=note)
            target.message_post(body=note)
            booking._notify('transport.email_template_rebook')
        return True

    def payment_method_label(self):
        self.ensure_one()
        return dict(self._fields['payment_method'].selection).get(self.payment_method, '')

    def _ensure_price(self):
        self.ensure_one()
        if self.amount_total:
            return
        price = self.departure_id.line_id.price_between(self.origin_stop_id, self.destination_stop_id)
        self.write({
            'fare_unit': price,
            'amount_total': price * self.seat_count,
        })

    def action_open_collect(self):
        self.ensure_one()
        if self.channel != 'b2c':
            raise UserError(_("L'abonné ne paie pas au guichet."))
        if self.paid:
            return self.action_print_receipt()
        if self.state not in ('held', 'confirmed'):
            raise UserError(_("Ce billet ne peut plus être encaissé."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Encaisser'),
            'res_model': 'transport.booking.collect',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_booking_id': self.id},
        }

    def pay_counter(self, method):
        """Confirm a counter sale and record cash or card-terminal payment."""
        self.ensure_one()
        if self.channel != 'b2c':
            raise UserError(_("L'abonné ne paie pas au guichet."))
        if method not in ('cash', 'tpe'):
            raise UserError(_("Choisissez espèces ou TPE."))
        if self.paid:
            if self.payment_method and self.payment_method != method:
                raise UserError(_("Ce billet est déjà encaissé (%s).", self.payment_method_label()))
            return self.ticket_id
        if self.state == 'held':
            self._ensure_price()
            self.action_confirm()
        elif self.state != 'confirmed':
            raise UserError(_("Ce billet ne peut plus être encaissé."))
        else:
            self._ensure_price()
        prefix = 'ESP' if method == 'cash' else 'TPE'
        self.write({
            'paid': True,
            'payment_method': method,
            'payment_reference': '%s-%s' % (prefix, self.id),
        })
        if not self.ticket_id:
            raise UserError(_("Le paiement n'a pas confirmé le billet."))
        return self.ticket_id

    def action_print_receipt(self):
        self.ensure_one()
        if not self.paid or not self.ticket_id:
            raise UserError(_("Aucun reçu : le billet n'est pas payé."))
        return self.env.ref('transport.action_report_receipt').with_context(
            discard_logo_check=True,
        ).report_action(self.ticket_id)

    def action_cancel(self):
        passenger = self.env.context.get('transport_passenger_cancel')
        for booking in self:
            if booking.state == 'boarded':
                raise UserError(_("Ce passager est déjà embarqué."))
            if booking.state not in ('held', 'confirmed'):
                raise UserError(_("Cette réservation ne peut plus être annulée."))
            if booking.departure_id.state in ('in_progress', 'done'):
                raise UserError(_("Le départ est déjà en course."))
            if passenger and booking.state == 'confirmed' and not booking.within_cancel_window():
                raise UserError(_("Le délai d'annulation est dépassé. Le billet reste confirmé."))
            refund = booking._refund_due()
            tickets = booking.ticket_ids
            booking.with_context(transport_booking_state=True).write({
                'state': 'cancelled',
                'refund_amount': refund,
            })
            if tickets:
                tickets.write({'state': 'cancelled'})
        if not self.env.context.get('transport_skip_waitlist_offer'):
            self.env['transport.waitlist'].offer_open(self.mapped('departure_id'))
        return True

    def cancel_for_closure(self):
        """Cancel a ticket because the company closed the service day. Paid seats are refunded in full."""
        reason = (self.env.context.get('transport_closure_reason') or '').strip()
        for booking in self:
            if booking.state == 'boarded':
                raise UserError(_("Ce passager est déjà embarqué."))
            if booking.state not in ('held', 'confirmed'):
                continue
            refund = booking.amount_total if booking.paid else 0.0
            tickets = booking.ticket_ids
            booking.with_context(
                transport_booking_state=True,
                transport_skip_waitlist_offer=True,
            ).write({
                'state': 'cancelled',
                'refund_amount': refund,
                'closure_reason': reason or False,
            })
            if tickets:
                tickets.write({'state': 'cancelled'})
            if reason:
                booking._notify('transport.email_template_closure')
        return True

    @api.model
    def book_public(self, departure_id, origin_id, destination_id, passenger_name, phone, email=None, seat_count=1, seat_numbers=None, seat_names=None):
        """Hold a seat, then send the passenger to payment."""
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
        stops = departure.line_id.stop_ids.stop_id
        if origin not in stops or destination not in stops:
            raise UserError(_("Choisissez la montée et la descente sur cette ligne."))
        price = departure.line_id.price_between(origin, destination)
        mail = (email or '').strip()
        phone_key = self._phone_key(phone)
        named = self.env['res.partner'].search([('name', '=ilike', name[:128])])
        partner = named.filtered(lambda item: self._phone_key(item.phone) == phone_key)[:1]
        if not partner:
            partner = self.env['res.partner'].create({
                'name': name[:128],
                'phone': phone[:32],
                'email': mail[:128] or False,
            })
        elif mail and not partner.email:
            partner.email = mail[:128]
        names = [name[:128]]
        for extra in seat_names or []:
            text = (extra or '').strip()
            if text:
                names.append(text[:128])
        booking = departure.book(
            origin, destination, seat_count, name[:128], partner=partner,
            seat_numbers=seat_numbers, seat_names=names,
        )
        vals = {
            'fare_unit': price,
            'amount_total': price * seat_count,
            'phone': phone[:32],
        }
        until = departure.effective_datetime or departure.departure_datetime
        if until and until > booking.hold_until:
            vals['hold_until'] = until
            booking.with_context(transport_extend_hold=True).write(vals)
        else:
            booking.write(vals)
        return booking

    def access_token(self):
        self.ensure_one()
        digest = hmac.new(
            self.env['transport.ticket']._secret().encode(),
            f'pay:{self.id}:{self.name}'.encode(),
            hashlib.sha256,
        ).hexdigest()[:24]
        return digest

    @api.model
    def _phone_key(self, value):
        digits = ''.join(character for character in (value or '') if character.isdigit())
        if digits.startswith('213') and len(digits) > 9:
            digits = digits[3:]
        return digits.lstrip('0')

    @api.model
    def find_public(self, reference, phone):
        """Open a ticket from its reference and the phone given at booking."""
        reference = (reference or '').strip()
        key = self._phone_key(phone)
        if len(reference) < 2 or len(key) < 6:
            raise UserError(_("Indiquez la référence du billet et le téléphone."))
        booking = self.sudo().search([('name', '=ilike', reference)], limit=1)
        stored = self._phone_key(booking.phone or booking.partner_id.phone or '')
        if not booking or stored != key:
            raise UserError(_("Billet introuvable."))
        return booking

    def _notify(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            return False
        sent = False
        for booking in self:
            if not booking.partner_id.email:
                continue
            template.send_mail(booking.id, force_send=False)
            sent = True
        return sent

    def pay_online(self):
        """Confirm the held seat and record the payment."""
        self.ensure_one()
        if self.channel != 'b2c':
            raise UserError(_("L'abonné ne paie pas en ligne."))
        if self.state == 'held':
            self.action_confirm()
            self.write({
                'paid': True,
                'payment_method': 'online',
                'payment_reference': 'PAY-%s' % self.id,
            })
        if self.state != 'confirmed' or not self.paid or not self.ticket_id:
            raise UserError(_("Le paiement n'a pas confirmé le billet."))
        return self.ticket_id

    @api.model
    def _cron_expire_holds(self):
        expired = self.search([
            ('state', '=', 'held'),
            ('hold_until', '<=', fields.Datetime.now()),
        ])
        if expired:
            departures = expired.departure_id
            expired.with_context(transport_booking_state=True).write({'state': 'cancelled'})
            self.env['transport.waitlist'].offer_open(departures)
        late = self.env['transport.waitlist'].search([
            ('state', '=', 'offered'),
            ('offer_until', '<=', fields.Datetime.now()),
        ])
        if late:
            self.env['transport.waitlist'].offer_open(late.departure_id)
        return True

    @api.model
    def _assign_missing_seats(self):
        pending = self.search([
            ('state', 'in', ('held', 'confirmed', 'boarded')),
            ('seat_ids', '=', False),
        ], order='departure_id, id')
        seats = self.env['transport.booking.seat']
        for booking in pending:
            numbers = booking.departure_id.choose_seat_numbers(
                booking._covered_legs(), booking.seat_count, None,
            )
            labels = booking._names_for_seats(len(numbers), None)
            seats.create([
                {
                    'booking_id': booking.id,
                    'number': number,
                    'passenger_name': label,
                }
                for number, label in zip(numbers, labels)
            ])
        return True


class TransportBookingSeat(models.Model):
    _name = 'transport.booking.seat'
    _description = 'Siège réservé'
    _order = 'number, id'

    booking_id = fields.Many2one(
        'transport.booking', string='Réservation', required=True, ondelete='cascade', index=True,
    )
    number = fields.Integer(string='Siège', required=True)
    passenger_name = fields.Char(string='Passager')

    _number_positive = models.Constraint(
        'CHECK(number > 0)',
        'Le numéro de siège doit être positif.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_available()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'number', 'booking_id'} & set(vals):
            self._check_available()
        return result

    def _check_available(self):
        now = fields.Datetime.now()
        for seat in self:
            booking = seat.booking_id
            if not booking or booking.state not in ('held', 'confirmed', 'boarded'):
                continue
            if booking.state == 'held' and (not booking.hold_until or booking.hold_until <= now):
                continue
            duplicate = booking.seat_ids.filtered(lambda other: other != seat and other.number == seat.number)
            if duplicate:
                raise UserError(_("Le siège %s est déjà sur cette réservation.", seat.number))
            clash = self.search([
                ('id', '!=', seat.id),
                ('number', '=', seat.number),
                ('booking_id.departure_id', '=', booking.departure_id.id),
                ('booking_id', '!=', booking.id),
                ('booking_id.state', 'in', ('held', 'confirmed', 'boarded')),
                ('booking_id.origin_sequence', '<', booking.destination_sequence),
                ('booking_id.destination_sequence', '>', booking.origin_sequence),
            ]).filtered(
                lambda other: other.booking_id.state != 'held' or (
                    other.booking_id.hold_until and other.booking_id.hold_until > now
                ),
            )
            if clash:
                raise UserError(_("Siège déjà pris sur ce trajet : %s.", seat.number))
