# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class TransportContract(models.Model):
    _name = 'transport.contract'
    _description = 'Contrat entreprise'
    _inherit = ['mail.thread']
    _order = 'name, id'

    name = fields.Char(string='Référence', required=True, copy=False, default='/', tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='Entreprise', required=True, tracking=True, index=True,
    )
    line_ids = fields.Many2many('transport.line', string='Lignes', required=True)
    date_start = fields.Date(string='Début', required=True, tracking=True)
    date_end = fields.Date(string='Fin', tracking=True)
    seat_quota = fields.Integer(
        string='Places garanties par départ', required=True, default=1, tracking=True,
        help="Nombre maximum de places abonnés de ce contrat sur un même départ.",
    )
    state = fields.Selection(
        [
            ('draft', 'Brouillon'),
            ('open', 'En cours'),
            ('closed', 'Clos'),
        ],
        string='Statut',
        default='draft',
        required=True,
        tracking=True,
    )
    subscriber_ids = fields.One2many('transport.subscriber', 'contract_id', string='Abonnés')

    _quota_positive = models.Constraint(
        'CHECK(seat_quota > 0)',
        'Le quota de places doit être positif.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.contract') or _('Nouveau')
            prepared.append(vals)
        return super().create(prepared)

    @api.constrains('date_start', 'date_end')
    def _dates_order(self):
        for contract in self:
            if contract.date_end and contract.date_end < contract.date_start:
                raise ValidationError(_("La fin du contrat est avant le début."))

    def action_open(self):
        for contract in self:
            if contract.state != 'draft':
                raise UserError(_("Seul un brouillon peut être ouvert."))
            if not contract.line_ids:
                raise UserError(_("Choisissez au moins une ligne."))
        self.write({'state': 'open'})
        return True

    def action_close(self):
        if any(contract.state != 'open' for contract in self):
            raise UserError(_("Seul un contrat en cours se clôt."))
        self.write({'state': 'closed'})
        return True

    def seats_on(self, departure):
        self.ensure_one()
        now = fields.Datetime.now()
        total = 0
        for booking in departure.booking_ids:
            if booking.subscriber_id.contract_id != self:
                continue
            if booking.state == 'held' and (not booking.hold_until or booking.hold_until <= now):
                continue
            if booking.state in ('held', 'confirmed', 'boarded'):
                total += booking.seat_count
        return total

    def statement_rows(self, date_from, date_to):
        """Trips of this company's subscribers between two dates. Not an invoice."""
        labels = dict(self.env['transport.booking']._fields['state'].selection)
        bookings = self.env['transport.booking'].search([
            ('channel', '=', 'b2b'),
            ('subscriber_id.contract_id', 'in', self.ids),
            ('state', 'in', ('confirmed', 'boarded', 'noshow')),
        ])
        rows = []
        for booking in bookings:
            day = booking.departure_id._service_date()
            if not day or day < date_from or day > date_to:
                continue
            rows.append({
                'id': booking.id,
                'date': day,
                'line': booking.departure_id.line_id.name,
                'name': booking.subscriber_id.name or booking.passenger_name,
                'origin': booking.origin_stop_id.name,
                'destination': booking.destination_stop_id.name,
                'seats': booking.seat_count,
                'detail': booking.seat_detail or booking.seat_label or '',
                'state': labels.get(booking.state, booking.state),
                'boarded': booking.state == 'boarded',
                'absent': booking.state == 'noshow',
            })
        rows.sort(key=lambda row: (row['date'], row['name'], row['id']))
        return rows

    def action_open_statement(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Relevé'),
            'res_model': 'transport.contract.statement',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.partner_id.id},
        }


class TransportSubscriber(models.Model):
    _name = 'transport.subscriber'
    _description = 'Abonné entreprise'
    _order = 'name, id'

    name = fields.Char(string='Nom', required=True)
    contract_id = fields.Many2one(
        'transport.contract', string='Contrat', required=True, ondelete='restrict', index=True,
    )
    partner_id = fields.Many2one('res.partner', string='Contact')
    date_start = fields.Date(string='Début')
    date_end = fields.Date(string='Fin')
    active = fields.Boolean(default=True)

    def covers(self, line, day):
        self.ensure_one()
        contract = self.contract_id
        if not self.active or contract.state != 'open' or line not in contract.line_ids:
            return False
        start = self.date_start or contract.date_start
        end = self.date_end or contract.date_end
        if start and day < start:
            return False
        if end and day > end:
            return False
        return True
