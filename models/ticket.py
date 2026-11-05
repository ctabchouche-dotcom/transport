# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import io
import secrets

import qrcode

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TransportTicket(models.Model):
    _name = 'transport.ticket'
    _description = 'Billet'
    _order = 'id desc'

    name = fields.Char(related='booking_id.name', store=True)
    booking_id = fields.Many2one(
        'transport.booking', string='Réservation', required=True, ondelete='cascade', index=True,
    )
    qr_payload = fields.Char(string='QR', required=True, copy=False, readonly=True)
    state = fields.Selection(
        [
            ('issued', 'Émis'),
            ('boarded', 'Embarqué'),
            ('noshow', 'No-show'),
            ('cancelled', 'Annulé'),
        ],
        string='Statut',
        default='issued',
        required=True,
        index=True,
    )

    _booking_unique = models.Constraint(
        'UNIQUE(booking_id)',
        'Cette réservation a déjà un billet.',
    )

    @api.model
    def _secret(self):
        params = self.env['ir.config_parameter'].sudo()
        secret = params.get_param('transport.qr_secret')
        if not secret:
            secret = secrets.token_hex(32)
            params.set_param('transport.qr_secret', secret)
        return secret

    @api.model
    def _payload_for(self, booking):
        digest = hmac.new(
            self._secret().encode(),
            f'{booking.id}:{booking.name}'.encode(),
            hashlib.sha256,
        ).hexdigest()[:20]
        return f'TRP:{booking.id}:{digest}'

    @api.model
    def issue(self, bookings):
        tickets = self.env['transport.ticket']
        for booking in bookings:
            if booking.ticket_id:
                tickets |= booking.ticket_id
                continue
            ticket = self.create({
                'booking_id': booking.id,
                'qr_payload': self._payload_for(booking),
            })
            ticket._send()
            tickets |= ticket
        return tickets

    def _signature_matches(self):
        self.ensure_one()
        expected = self._payload_for(self.booking_id)
        return hmac.compare_digest(self.qr_payload or '', expected)

    def qr_src(self):
        """PNG data URI drawn with Pillow, without ReportLab's Cairo backend."""
        self.ensure_one()
        image = qrcode.make(self.qr_payload or '')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        encoded = base64.b64encode(buffer.getvalue()).decode()
        return 'data:image/png;base64,%s' % encoded

    def _send(self):
        self.ensure_one()
        partner = self.booking_id.partner_id
        if not partner or not partner.email:
            return False
        template = self.env.ref('transport.email_template_ticket', raise_if_not_found=False)
        if not template:
            return False
        template.send_mail(self.id, force_send=False)
        return True

    def write(self, vals):
        if {'booking_id', 'qr_payload'} & set(vals):
            raise UserError(_("Le QR d'un billet émis ne se réécrit pas."))
        return super().write(vals)

    @api.model
    def board_payload(self, payload, departure):
        payload = (payload or '').strip()
        ticket = self.search([('qr_payload', '=', payload)], limit=1)
        if not ticket or not ticket._signature_matches():
            raise UserError(_("Billet refusé."))
        if ticket.booking_id.departure_id != departure:
            raise UserError(_("Ce billet est pour un autre départ."))
        if ticket.state == 'cancelled':
            raise UserError(_("Ce billet est annulé."))
        ticket.booking_id.action_board()
        return ticket
