# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class TransportBoardScan(models.TransientModel):
    _name = 'transport.board.scan'
    _description = 'Scanner un billet'

    departure_id = fields.Many2one('transport.departure', string='Départ', required=True)
    payload = fields.Char(string='QR du billet', required=True)

    def action_board(self):
        self.ensure_one()
        ticket = self.env['transport.ticket'].board_payload(self.payload, self.departure_id)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Embarqué'),
                'message': _('%s est à bord.', ticket.booking_id.passenger_name),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
