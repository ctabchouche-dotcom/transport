# -*- coding: utf-8 -*-
import re

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class TransportDevice(http.Controller):
    """Fixed GPS tracker and door QR reader installed in one bus.

    The devices call these addresses themselves. No driver phone is involved.
    HTTP 200 means the point was stored, or the passenger may pass.
    Any other status means refuse.
    """

    def _vehicle(self, token):
        if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
            return request.env['fleet.vehicle']
        vehicle = request.env['fleet.vehicle'].sudo().search([
            ('transport_device_token', '=', token),
        ], limit=1)
        return vehicle

    def _text(self, body, status):
        return request.make_response(
            (body or '').encode('utf-8'),
            headers=[('Content-Type', 'text/plain; charset=utf-8')],
            status=status,
        )

    def _values(self):
        values = dict(request.params or {})
        incoming = request.httprequest.get_json(silent=True)
        if isinstance(incoming, dict):
            values.update(incoming)
        return values

    @http.route(
        ['/bus/<string:token>/position'],
        type='http', auth='public', methods=['GET', 'POST'], csrf=False, website=False, sitemap=False,
    )
    def position(self, token, **kw):
        vehicle = self._vehicle(token)
        if not vehicle:
            return self._text('Bus inconnu.', 404)
        values = self._values()
        latitude = values.get('latitude', values.get('lat'))
        longitude = values.get('longitude', values.get('lon', values.get('lng')))
        try:
            vehicle.device_record_position(latitude, longitude)
        except UserError as err:
            return self._text(err.args[0] if err.args else 'Position refusée.', 409)
        return self._text('ok', 200)

    @http.route(
        ['/bus/<string:token>/scan'],
        type='http', auth='public', methods=['GET', 'POST'], csrf=False, website=False, sitemap=False,
    )
    def scan(self, token, **kw):
        vehicle = self._vehicle(token)
        if not vehicle:
            return self._text('Bus inconnu.', 404)
        values = self._values()
        payload = values.get('payload') or values.get('code') or values.get('qr') or values.get('data')
        try:
            ticket = vehicle.device_board(payload)
        except UserError as err:
            return self._text(err.args[0] if err.args else 'Billet refusé.', 409)
        return self._text(ticket.booking_id.passenger_name or 'ok', 200)
