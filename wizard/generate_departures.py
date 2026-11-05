# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _


class TransportDepartureGenerate(models.TransientModel):
    _name = 'transport.departure.generate'
    _description = 'Générer les départs'

    line_id = fields.Many2one('transport.line', string='Ligne', required=True)
    date_from = fields.Date(
        string='Du', required=True, default=fields.Date.context_today,
    )
    date_to = fields.Date(string='Au', required=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'date_to' in fields_list and not vals.get('date_to'):
            start = fields.Date.to_date(vals.get('date_from')) or fields.Date.context_today(self)
            vals['date_to'] = start + timedelta(days=30)
        return vals

    def action_generate(self):
        self.ensure_one()
        departures = self.line_id.generate_departures(self.date_from, self.date_to)
        if not departures:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Départs'),
                    'message': _('Aucun nouveau départ : ces créneaux existent déjà.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Départs générés'),
            'res_model': 'transport.departure',
            'view_mode': 'list,form',
            'domain': [('id', 'in', departures.ids)],
            'target': 'current',
        }
