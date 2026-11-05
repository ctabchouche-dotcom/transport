# -*- coding: utf-8 -*-
import hmac

import pytz

from odoo import fields, http, _
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

WEEKDAYS = ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')


def transport_tz_name():
    user = request.env.user
    company_tz = request.env.company.sudo().partner_id.tz
    return user.tz or company_tz or 'Africa/Algiers'


def transport_tz():
    return pytz.timezone(transport_tz_name())


def utc_to_local(value):
    if not value:
        return None
    return pytz.UTC.localize(value).astimezone(transport_tz())


class TransportBookingPage(http.Controller):

    def _company(self):
        return request.env.company.sudo().name or _("Transport")

    def _departures(self):
        return request.env['transport.departure'].sudo().search([
            ('state', 'in', ('planned', 'assigned', 'boarding')),
            ('effective_datetime', '>', fields.Datetime.now()),
            ('line_id.line_type', '!=', 'b2b'),
            ('line_id.active', '=', True),
        ], order='effective_datetime, id')

    def _lines(self):
        return self._departures().line_id.sorted('name')

    def _days(self, line):
        days = []
        index = {}
        departures = self._departures().filtered(lambda item: item.line_id == line)
        for departure in departures:
            local = utc_to_local(departure.effective_datetime or departure.departure_datetime)
            key = local.strftime('%Y-%m-%d')
            if key not in index:
                index[key] = {
                    'key': key,
                    'label': '%s %s' % (WEEKDAYS[local.weekday()], local.strftime('%d/%m')),
                    'hours': [],
                }
                days.append(index[key])
            label = local.strftime('%H:%M')
            if departure.delay_minutes:
                moved = utc_to_local(departure.effective_datetime)
                label = '%s · prévu %s' % (moved.strftime('%H:%M'), label)
            index[key]['hours'].append({
                'id': departure.id,
                'label': label,
            })
        return days

    def _fares(self, line):
        return [{
            'origin': fare.origin_stop_id.name,
            'destination': fare.destination_stop_id.name,
            'price': self._money(fare.price),
        } for fare in line.fare_ids.sorted(lambda fare: (fare.origin_stop_id.name, fare.destination_stop_id.name))]

    def _selected_departure(self, line, day, form):
        if not line or not day or not day.get('hours'):
            return request.env['transport.departure']
        departure_id = self._int((form or {}).get('departure_id')) or day['hours'][0]['id']
        departure = request.env['transport.departure'].sudo().browse(departure_id).exists()
        if not departure or departure.line_id != line:
            return request.env['transport.departure']
        return departure

    def _passages(self, line, day, form):
        departure = self._selected_departure(line, day, form)
        if not departure:
            return []
        rows = []
        for line_stop in departure.line_id.stop_ids.sorted('sequence'):
            local = utc_to_local(departure.stop_passage(line_stop.stop_id))
            rows.append({
                'name': line_stop.stop_id.name,
                'time': local.strftime('%H:%M') if local else '',
            })
        return rows

    def _seats_free(self, line, day, form):
        departure = self._selected_departure(line, day, form)
        if not departure:
            return None
        stops = line.stop_ids.sorted('sequence')
        origin = request.env['transport.stop'].sudo().browse(
            self._int((form or {}).get('origin_stop_id')) or stops[:1].stop_id.id,
        )
        destination = request.env['transport.stop'].sudo().browse(
            self._int((form or {}).get('destination_stop_id')) or stops[-1:].stop_id.id,
        )
        try:
            return departure.b2c_free_between(origin, destination)
        except UserError:
            return None

    def _booking_passages(self, booking):
        rows = []
        for line_stop in booking.departure_id.line_id.stop_ids.sorted('sequence'):
            local = utc_to_local(booking.departure_id.stop_passage(line_stop.stop_id))
            rows.append({
                'name': line_stop.stop_id.name,
                'time': local.strftime('%H:%M') if local else '',
            })
        return rows

    def _seat_plan(self, line, day, form):
        if not line or not day or not day.get('hours'):
            return None
        departure_id = self._int((form or {}).get('departure_id')) or day['hours'][0]['id']
        departure = request.env['transport.departure'].sudo().browse(departure_id).exists()
        if not departure or departure.line_id != line:
            return None
        stops = line.stop_ids.sorted('sequence')
        origin = request.env['transport.stop'].sudo().browse(
            self._int((form or {}).get('origin_stop_id')) or stops[:1].stop_id.id,
        )
        destination = request.env['transport.stop'].sudo().browse(
            self._int((form or {}).get('destination_stop_id')) or stops[-1:].stop_id.id,
        )
        try:
            legs, _origin_sequence, _destination_sequence = departure._legs_between(origin, destination)
        except UserError:
            return None
        at = fields.Datetime.now()
        taken = set()
        for booking in departure.booking_ids:
            if any(booking._occupies_leg(leg, at) for leg in legs):
                taken.update(booking.seat_ids.mapped('number'))
        return departure.seat_plan(taken)

    def _stops(self, line):
        return [{
            'id': stop.stop_id.id,
            'name': stop.stop_id.name,
        } for stop in line.stop_ids.sorted('sequence')]

    def _values(self, **extra):
        line_id = extra.pop('line_id', None)
        day = extra.pop('day', None)
        lines = self._lines()
        line = lines.filtered(lambda item: item.id == line_id)[:1]
        days = self._days(line) if line else []
        stops = self._stops(line) if line else []
        chosen = next((item for item in days if item['key'] == day), None)
        values = {
            'company': self._company(),
            'lines': lines,
            'line': line,
            'days': days,
            'day': chosen,
            'stops': stops,
            'origin_default': stops[0]['id'] if stops else '',
            'destination_default': stops[-1]['id'] if stops else '',
            'fares': self._fares(line) if line else [],
            'passages': self._passages(line, chosen, extra.get('form') or {}),
            'seats_free': self._seats_free(line, chosen, extra.get('form') or {}),
            'seat_plan': self._seat_plan(line, chosen, extra.get('form') or {}),
            'error': None,
            'form': {},
        }
        values.update(extra)
        return values

    @http.route(['/reserver-un-billet'], type='http', auth='public', website=False, sitemap=False)
    def booking_form(self, line_id=None, day=None, departure_id=None, origin_stop_id=None, destination_stop_id=None, **kw):
        try:
            line_id = int(line_id) if line_id else None
        except (TypeError, ValueError):
            line_id = None
        form = {}
        if departure_id:
            form['departure_id'] = departure_id
        if origin_stop_id:
            form['origin_stop_id'] = origin_stop_id
        if destination_stop_id:
            form['destination_stop_id'] = destination_stop_id
        return request.render('transport.booking_page', self._values(
            line_id=line_id, day=day, form=form,
        ))

    @http.route(
        ['/reserver-un-billet/envoyer'],
        type='http', auth='public', methods=['POST'], website=False, sitemap=False, csrf=True,
    )
    def booking_submit(self, **kw):
        form = {
            'departure_id': kw.get('departure_id') or '',
            'origin_stop_id': kw.get('origin_stop_id') or '',
            'destination_stop_id': kw.get('destination_stop_id') or '',
            'passenger_name': (kw.get('passenger_name') or '').strip(),
            'phone': (kw.get('phone') or '').strip(),
            'email': (kw.get('email') or '').strip(),
            'seat_count': kw.get('seat_count') or '1',
        }
        departure = request.env['transport.departure'].sudo().browse(
            self._int(form['departure_id']),
        ).exists()
        shown = (departure.effective_datetime or departure.departure_datetime) if departure else None
        local = utc_to_local(shown) if shown else None
        try:
            booking = request.env['transport.booking'].sudo().book_public(
                self._int(form['departure_id']),
                self._int(form['origin_stop_id']),
                self._int(form['destination_stop_id']),
                form['passenger_name'],
                form['phone'],
                email=form['email'],
                seat_count=form['seat_count'],
                seat_numbers=request.httprequest.form.getlist('seat_number'),
                seat_names=request.httprequest.form.getlist('seat_passenger'),
            )
        except (UserError, ValidationError) as err:
            return request.render('transport.booking_page', self._values(
                line_id=departure.line_id.id if departure else None,
                day=local.strftime('%Y-%m-%d') if local else None,
                error=err.args[0] if err.args else _("La demande n'a pas pu être envoyée."),
                form=form,
            ))
        return request.redirect('/reserver-un-billet/paiement/%s/%s' % (
            booking.id, booking.access_token(),
        ))

    @http.route(
        ['/reserver-un-billet/attente'],
        type='http', auth='public', methods=['POST'], website=False, sitemap=False, csrf=True,
    )
    def waitlist_join(self, **kw):
        try:
            entry = request.env['transport.waitlist'].sudo().join_public(
                self._int(kw.get('departure_id')),
                self._int(kw.get('origin_stop_id')),
                self._int(kw.get('destination_stop_id')),
                kw.get('passenger_name'),
                kw.get('phone'),
                email=kw.get('email'),
                seat_count=kw.get('seat_count') or 1,
            )
        except (UserError, ValidationError) as err:
            departure = request.env['transport.departure'].sudo().browse(
                self._int(kw.get('departure_id')),
            ).exists()
            shown = (departure.effective_datetime or departure.departure_datetime) if departure else None
            local = utc_to_local(shown) if shown else None
            return request.render('transport.booking_page', self._values(
                line_id=departure.line_id.id if departure else None,
                day=local.strftime('%Y-%m-%d') if local else None,
                error=err.args[0] if err.args else _("La liste d'attente n'a pas pu être ouverte."),
                form={
                    'departure_id': kw.get('departure_id') or '',
                    'origin_stop_id': kw.get('origin_stop_id') or '',
                    'destination_stop_id': kw.get('destination_stop_id') or '',
                    'passenger_name': (kw.get('passenger_name') or '').strip(),
                    'phone': (kw.get('phone') or '').strip(),
                    'email': (kw.get('email') or '').strip(),
                    'seat_count': kw.get('seat_count') or '1',
                },
            ))
        return request.render('transport.waitlist_done', {
            'company': self._company(),
            'entry': entry,
        })

    @http.route(
        ['/reserver-un-billet/attente/<int:entry_id>/<string:token>'],
        type='http', auth='public', methods=['GET', 'POST'], website=False, sitemap=False, csrf=True,
    )
    def waitlist_claim(self, entry_id, token, **kw):
        entry = request.env['transport.waitlist'].sudo().browse(entry_id).exists()
        if not entry or len(token or '') != 24 or not hmac.compare_digest(entry.access_token(), token):
            return request.not_found()
        error = None
        if request.httprequest.method == 'POST':
            try:
                booking = entry.claim()
            except (UserError, ValidationError) as err:
                error = err.args[0] if err.args else _("La place n'a pas pu être prise.")
            else:
                return request.redirect('/reserver-un-billet/paiement/%s/%s' % (
                    booking.id, booking.access_token(),
                ))
        return request.render('transport.waitlist_offer', {
            'company': self._company(),
            'entry': entry,
            'error': error,
            'token': token,
        })

    @http.route(
        ['/reserver-un-billet/retrouver'],
        type='http', auth='public', methods=['GET', 'POST'], website=False, sitemap=False, csrf=True,
    )
    def find_ticket(self, **kw):
        error = None
        form = {
            'reference': (kw.get('reference') or '').strip(),
            'phone': (kw.get('phone') or '').strip(),
        }
        if request.httprequest.method == 'POST':
            try:
                booking = request.env['transport.booking'].sudo().find_public(
                    form['reference'], form['phone'],
                )
            except (UserError, ValidationError):
                booking = request.env['transport.booking']
            if booking:
                return request.redirect('/reserver-un-billet/paiement/%s/%s' % (
                    booking.id, booking.access_token(),
                ))
            try:
                entry = request.env['transport.waitlist'].sudo().find_public(
                    form['reference'], form['phone'],
                )
            except (UserError, ValidationError) as err:
                error = err.args[0] if err.args else _("Billet introuvable.")
            else:
                if entry.state == 'offered':
                    return request.redirect('/reserver-un-billet/attente/%s/%s' % (
                        entry.id, entry.access_token(),
                    ))
                if entry.state == 'booked' and entry.booking_id:
                    return request.redirect('/reserver-un-billet/paiement/%s/%s' % (
                        entry.booking_id.id, entry.booking_id.access_token(),
                    ))
                error = _("Vous êtes en liste d'attente. La place vous sera proposée dès qu'elle se libère.")
        return request.render('transport.find_ticket', {
            'company': self._company(),
            'error': error,
            'form': form,
        })

    @http.route(
        ['/reserver-un-billet/paiement/<int:booking_id>/<string:token>'],
        type='http', auth='public', methods=['GET', 'POST'], website=False, sitemap=False, csrf=True,
    )
    def payment(self, booking_id, token, **kw):
        booking = self._paid_booking(booking_id, token)
        if not booking:
            return request.not_found()
        error = None
        if request.httprequest.method == 'POST':
            try:
                ticket = booking.pay_online()
            except (UserError, ValidationError) as err:
                error = err.args[0] if err.args else _("Le paiement a échoué.")
            else:
                content, report_type = request.env['ir.actions.report'].sudo().with_context(
                    discard_logo_check=True,
                )._render_qweb_pdf('transport.action_report_receipt', ticket.ids)
                filename = 'Recu_%s.%s' % (booking.name or booking.id, 'pdf' if report_type == 'pdf' else 'html')
                mimetype = 'application/pdf' if report_type == 'pdf' else 'text/html'
                return request.make_response(content, headers=[
                    ('Content-Type', mimetype),
                    ('Content-Disposition', 'attachment; filename="%s"' % filename),
                ])
        return self._payment_page(booking, token, error)

    @http.route(
        ['/reserver-un-billet/annuler/<int:booking_id>/<string:token>'],
        type='http', auth='public', methods=['POST'], website=False, sitemap=False, csrf=True,
    )
    def cancel(self, booking_id, token, **kw):
        booking = self._paid_booking(booking_id, token)
        if not booking:
            return request.not_found()
        try:
            booking.with_context(transport_passenger_cancel=True).action_cancel()
        except (UserError, ValidationError) as err:
            return self._payment_page(
                booking, token, err.args[0] if err.args else _("L'annulation a échoué."),
            )
        return request.redirect('/reserver-un-billet/paiement/%s/%s' % (booking.id, token))

    def _paid_booking(self, booking_id, token):
        booking = request.env['transport.booking'].sudo().browse(booking_id).exists()
        if not booking or len(token or '') != 24 or not hmac.compare_digest(booking.access_token(), token):
            return request.env['transport.booking']
        return booking

    def _payment_page(self, booking, token, error=None):
        moment = booking.departure_id.effective_datetime or booking.departure_id.departure_datetime
        local = utc_to_local(moment)
        when = '%s %s' % (WEEKDAYS[local.weekday()], local.strftime('%d/%m/%Y %H:%M'))
        if booking.departure_id.delay_minutes:
            when = '%s (retard %s min)' % (when, booking.departure_id.delay_minutes)
        confirmed = booking.state == 'confirmed'
        return request.render('transport.payment_page', {
            'company': self._company(),
            'booking': booking,
            'when': when,
            'passages': self._booking_passages(booking),
            'amount': self._money(booking.amount_total),
            'unit': self._money(booking.fare_unit),
            'refund': self._money(booking.refund_amount),
            'rule': booking.cancel_rule_label(),
            'error': error,
            'token': token,
            'can_pay': booking.state == 'held',
            'can_download': confirmed and booking.paid,
            'can_cancel': booking.state == 'held' or (
                confirmed and booking.within_cancel_window()
                and booking.departure_id.state not in ('in_progress', 'done')
            ),
        })

    def _money(self, amount):
        return '%s DZD' % ('{:,.0f}'.format(amount or 0).replace(',', ' '))

    def _int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
