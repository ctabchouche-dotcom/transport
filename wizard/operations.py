# -*- coding: utf-8 -*-
from calendar import monthrange

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TransportDepartureDelay(models.TransientModel):
    _name = 'transport.departure.delay'
    _description = 'Annoncer un retard'

    departure_id = fields.Many2one('transport.departure', required=True)
    delay_minutes = fields.Integer(string='Retard (minutes)', required=True, default=15)
    reason = fields.Char(string='Motif')

    def action_apply(self):
        self.ensure_one()
        self.departure_id.set_delay(self.delay_minutes, self.reason)
        return {'type': 'ir.actions.act_window_close'}


class TransportDepartureSwap(models.TransientModel):
    _name = 'transport.departure.swap'
    _description = 'Remplacer le bus'

    departure_id = fields.Many2one('transport.departure', required=True)
    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Bus de remplacement', required=True,
    )

    def action_apply(self):
        self.ensure_one()
        self.departure_id.swap_vehicle(self.vehicle_id)
        return {'type': 'ir.actions.act_window_close'}


class TransportBookingCollect(models.TransientModel):
    _name = 'transport.booking.collect'
    _description = 'Encaisser au guichet'

    booking_id = fields.Many2one('transport.booking', required=True)
    passenger_name = fields.Char(related='booking_id.passenger_name')
    seat_label = fields.Char(related='booking_id.seat_label')
    amount = fields.Float(string='Montant', compute='_compute_amount')
    method = fields.Selection(
        [('cash', 'Espèces'), ('tpe', 'TPE')],
        string='Mode', required=True, default='cash',
    )

    @api.depends('booking_id')
    def _compute_amount(self):
        for wizard in self:
            booking = wizard.booking_id
            if not booking:
                wizard.amount = 0
                continue
            if booking.amount_total:
                wizard.amount = booking.amount_total
                continue
            try:
                price = booking.departure_id.line_id.price_between(
                    booking.origin_stop_id, booking.destination_stop_id,
                )
            except UserError:
                price = 0
            wizard.amount = price * (booking.seat_count or 0)

    def action_apply(self):
        self.ensure_one()
        self.booking_id.pay_counter(self.method)
        return self.booking_id.action_print_receipt()


class TransportBookingRebook(models.TransientModel):
    _name = 'transport.booking.rebook'
    _description = 'Reporter un billet'

    booking_id = fields.Many2one('transport.booking', required=True)
    line_id = fields.Many2one(related='booking_id.line_id')
    source_departure_id = fields.Many2one(related='booking_id.departure_id')
    departure_id = fields.Many2one(
        'transport.departure', string='Nouveau départ', required=True,
        domain="[('line_id', '=', line_id), ('id', '!=', source_departure_id), ('state', 'in', ('planned', 'assigned', 'boarding'))]",
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        booking = self.env['transport.booking'].browse(self.env.context.get('default_booking_id'))
        if booking and booking.state not in ('held', 'confirmed'):
            raise UserError(_("Seule une réservation en attente ou confirmée se reporte."))
        return vals

    def action_apply(self):
        self.ensure_one()
        self.booking_id.action_rebook(self.departure_id)
        return {'type': 'ir.actions.act_window_close'}


class TransportDepartureClose(models.TransientModel):
    _name = 'transport.departure.close'
    _description = 'Fermer une journée'

    line_id = fields.Many2one(
        'transport.line', string='Ligne',
        help="Laissez vide pour fermer toutes les lignes ce jour-là.",
    )
    service_date = fields.Date(string='Jour', required=True, default=fields.Date.context_today)
    reason = fields.Char(string='Motif', required=True)

    def action_apply(self):
        self.ensure_one()
        closed, kept = self.env['transport.departure'].close_service_day(
            self.service_date, self.reason, self.line_id,
        )
        if not closed and not kept:
            message = _("Aucun départ ouvert ce jour-là.")
            kind = 'warning'
        elif kept:
            message = _(
                "%s départ(s) fermé(s). %s départ(s) gardé(s) : des passagers sont déjà embarqués.",
                len(closed), len(kept),
            )
            kind = 'warning'
        else:
            message = _("%s départ(s) fermé(s).", len(closed))
            kind = 'success'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Fermeture'),
                'message': message,
                'type': kind,
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class TransportContractStatement(models.TransientModel):
    _name = 'transport.contract.statement'
    _description = 'Relevé entreprise'

    partner_id = fields.Many2one('res.partner', string='Entreprise', required=True)
    date_from = fields.Date(string='Du', required=True)
    date_to = fields.Date(string='Au', required=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        last = monthrange(today.year, today.month)[1]
        values.setdefault('date_from', today.replace(day=1))
        values.setdefault('date_to', today.replace(day=last))
        return values

    def _contracts(self):
        self.ensure_one()
        return self.env['transport.contract'].search([
            ('partner_id', '=', self.partner_id.id),
        ])

    def statement(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_("La fin du relevé est avant le début."))
        rows = self._contracts().statement_rows(self.date_from, self.date_to)
        return {
            'rows': rows,
            'seats': sum(row['seats'] for row in rows),
            'boarded': sum(row['seats'] for row in rows if row['boarded']),
            'absent': sum(row['seats'] for row in rows if row['absent']),
        }

    def action_print(self):
        self.ensure_one()
        self.statement()
        return self.env.ref('transport.action_report_statement').with_context(
            discard_logo_check=True,
        ).report_action(self)


class TransportInsightLine(models.TransientModel):
    _name = 'transport.insight.line'
    _description = 'Statistique de ligne'
    _order = 'fill_percent desc, id'

    insight_id = fields.Many2one('transport.insight', required=True, ondelete='cascade')
    line_id = fields.Many2one('transport.line', string='Ligne')
    departures = fields.Integer(string='Départs')
    seats_sold = fields.Integer(string='Places vendues')
    seats_offered = fields.Integer(string='Places offertes')
    fill_percent = fields.Integer(string='Remplissage (%)')
    waiting = fields.Integer(string='Liste d\'attente')
    margin = fields.Float(string='Marge')
    top_trip = fields.Char(string='Trajet le plus demandé')


class TransportInsightAdvice(models.TransientModel):
    _name = 'transport.insight.advice'
    _description = 'Proposition'
    _order = 'id'

    insight_id = fields.Many2one('transport.insight', required=True, ondelete='cascade')
    kind = fields.Selection(
        [('high', 'Forte demande'), ('low', 'Demande basse'), ('note', 'Note')],
        string='Type',
    )
    summary = fields.Char(string='Proposition')


class TransportInsight(models.TransientModel):
    _name = 'transport.insight'
    _description = 'Statistiques et propositions'

    date_from = fields.Date(string='Du', required=True)
    date_to = fields.Date(string='Au', required=True)
    amount_collected = fields.Float(string='Encaissé', readonly=True)
    amount_cost = fields.Float(string='Charges', readonly=True)
    amount_profit = fields.Float(string='Profit', readonly=True)
    line_ids = fields.One2many('transport.insight.line', 'insight_id', string='Lignes')
    advice_ids = fields.One2many('transport.insight.advice', 'insight_id', string='Propositions')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        last = monthrange(today.year, today.month)[1]
        values.setdefault('date_from', today.replace(day=1))
        values.setdefault('date_to', today.replace(day=last))
        return values

    def _departures(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_("La fin de la période est avant le début."))
        found = self.env['transport.departure'].search([
            ('state', '!=', 'cancelled'),
        ])
        return found.filtered(
            lambda departure: self.date_from <= departure._service_date() <= self.date_to,
        )

    def _top_trip(self, bookings):
        totals = {}
        for booking in bookings:
            if booking.state not in ('confirmed', 'boarded', 'noshow'):
                continue
            key = '%s → %s' % (booking.origin_stop_id.name, booking.destination_stop_id.name)
            totals[key] = totals.get(key, 0) + booking.seat_count
        if not totals:
            return ''
        label = max(totals, key=totals.get)
        return '%s (%s places)' % (label, totals[label])

    def _smaller_bus(self, needed):
        vehicles = self.env['fleet.vehicle'].search([('seats', '>', 0), ('seats', '>=', needed)])
        if not vehicles:
            return 0
        return min(vehicles.mapped('seats'))

    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.advice_ids.unlink()
        departures = self._departures()
        collected = sum(departures.mapped('amount_collected'))
        cost = sum(departures.mapped('amount_cost'))
        self.write({
            'amount_collected': collected,
            'amount_cost': cost,
            'amount_profit': collected - cost,
        })
        Line = self.env['transport.insight.line']
        Advice = self.env['transport.insight.advice']
        for line in departures.line_id:
            group = departures.filtered(lambda item, current=line: item.line_id == current)
            offered = sum(group.mapped('seat_capacity'))
            sold = sum(group.mapped('seats_sold'))
            waiting = self.env['transport.waitlist'].search_count([
                ('departure_id', 'in', group.ids),
                ('state', 'in', ('waiting', 'offered', 'booked')),
            ])
            fill = round(sold * 100 / offered) if offered else 0
            peak = max(group.mapped('seats_sold') or [0])
            capacity = max(group.mapped('seat_capacity') or [0])
            Line.create({
                'insight_id': self.id,
                'line_id': line.id,
                'departures': len(group),
                'seats_sold': sold,
                'seats_offered': offered,
                'fill_percent': fill,
                'waiting': waiting,
                'margin': sum(group.mapped('amount_margin')),
                'top_trip': self._top_trip(group.booking_ids),
            })
            if fill >= 75 or waiting >= 2:
                Advice.create({
                    'insight_id': self.id,
                    'kind': 'high',
                    'summary': _(
                        "%s est très demandée (%s %%, %s en attente). Ajouter un départ. Trajet principal : %s.",
                        line.name, fill, waiting, self._top_trip(group.booking_ids) or _("aucun"),
                    ),
                })
            smaller = self._smaller_bus(max(peak, 1))
            if fill <= 40 and len(group) >= 1 and smaller and smaller < capacity:
                Advice.create({
                    'insight_id': self.id,
                    'kind': 'low',
                    'summary': _(
                        "%s est peu remplie (%s %%). Le pic est de %s places : un bus de %s places suffit et baisse les charges.",
                        line.name, fill, peak, smaller,
                    ),
                })
        if not departures:
            Advice.create({
                'insight_id': self.id,
                'kind': 'note',
                'summary': _("Aucun départ sur cette période."),
            })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Statistiques'),
            'res_model': 'transport.insight',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
