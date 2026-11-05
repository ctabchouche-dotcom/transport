# -*- coding: utf-8 -*-
import hmac

from odoo import http
from odoo.http import request


class TransportTracking(http.Controller):

    def _departure(self, departure_id, token):
        departure = request.env['transport.departure'].sudo().browse(departure_id).exists()
        if not departure or len(token or '') != 24:
            return request.env['transport.departure']
        if not hmac.compare_digest(departure.track_token(), token):
            return request.env['transport.departure']
        return departure

    @http.route(
        ['/suivi-bus/<int:departure_id>/<string:token>'],
        type='http', auth='user', methods=['GET'], website=False, sitemap=False,
    )
    def track(self, departure_id, token, **kw):
        departure = self._departure(departure_id, token)
        if not departure:
            return request.not_found()
        if not request.env.user.has_group('transport.group_transport_dispatcher'):
            return request.not_found()
        return request.render('transport.tracking_page', {
            'company': request.env.company.name or 'Transport',
            'departure': departure,
        })
