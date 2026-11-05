# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.exceptions import UserError
from odoo.http import request


class TransportBoarding(http.Controller):

    def _departure(self, departure_id):
        if not request.env.user.has_group('transport.group_transport_dispatcher'):
            return request.env['transport.departure']
        return request.env['transport.departure'].browse(departure_id).exists()

    @http.route(
        ['/embarquer/<int:departure_id>'],
        type='http', auth='user', methods=['GET', 'POST'], website=False, sitemap=False, csrf=True,
    )
    def board(self, departure_id, payload=None, **kw):
        departure = self._departure(departure_id)
        if not departure:
            return request.not_found()
        scanning = departure.state in ('boarding', 'in_progress')
        error = None
        notice = None
        if not scanning:
            error = _("Le scan est ouvert pendant l'embarquement et la course.")
        elif request.httprequest.method == 'POST':
            try:
                ticket = request.env['transport.ticket'].board_payload(payload, departure)
            except UserError as err:
                error = err.args[0] if err.args else _("Billet refusé.")
            else:
                notice = _("%s est à bord.", ticket.booking_id.passenger_name)
        return request.render('transport.boarding_page', {
            'company': request.env.company.name or 'Transport',
            'departure': departure,
            'scanning': scanning,
            'error': error,
            'notice': notice,
        })
