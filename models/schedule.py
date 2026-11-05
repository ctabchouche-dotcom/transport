# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TransportSchedule(models.Model):
    _name = 'transport.schedule'
    _description = 'Horaire type'
    _order = 'time_departure, id'

    name = fields.Char(string='Nom', required=True)
    line_id = fields.Many2one(
        'transport.line', string='Ligne', required=True, ondelete='cascade', index=True,
    )
    time_departure = fields.Float(
        string='Heure au départ', required=True, default=8.0,
        help="Heure de passage au premier arrêt.",
    )
    mon = fields.Boolean(string='Lun', default=True)
    tue = fields.Boolean(string='Mar', default=True)
    wed = fields.Boolean(string='Mer', default=True)
    thu = fields.Boolean(string='Jeu', default=True)
    fri = fields.Boolean(string='Ven', default=True)
    sat = fields.Boolean(string='Sam', default=True)
    sun = fields.Boolean(string='Dim', default=True)
    date_start = fields.Date(string='Du')
    date_end = fields.Date(string='Au')
    active = fields.Boolean(default=True)

    _time_range = models.Constraint(
        'CHECK(time_departure >= 0 AND time_departure < 24)',
        "L'heure de départ est invalide.",
    )

    @api.constrains('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
    def _at_least_one_day(self):
        for schedule in self:
            if not any(schedule[day] for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')):
                raise ValidationError("Cochez au moins un jour de circulation.")

    @api.constrains('date_start', 'date_end')
    def _season_order(self):
        for schedule in self:
            if schedule.date_start and schedule.date_end and schedule.date_end < schedule.date_start:
                raise ValidationError("La fin de saison est avant le début.")

    def matches(self, day):
        self.ensure_one()
        flags = (self.mon, self.tue, self.wed, self.thu, self.fri, self.sat, self.sun)
        if not flags[day.weekday()]:
            return False
        if self.date_start and day < self.date_start:
            return False
        if self.date_end and day > self.date_end:
            return False
        return True

    def as_datetime(self, day):
        """Naive UTC datetime for this schedule on ``day``."""
        self.ensure_one()
        hours = int(self.time_departure)
        minutes = int(round((self.time_departure - hours) * 60))
        if minutes == 60:
            hours += 1
            minutes = 0
        if hours >= 24:
            day = day + timedelta(days=1)
            hours -= 24
        company = self.line_id.company_id or self.env.company
        tzname = (
            self.env.context.get('tz')
            or self.env.user.tz
            or company.partner_id.tz
            or 'Africa/Algiers'
        )
        try:
            tz = pytz.timezone(tzname)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC
        local = tz.localize(datetime.combine(day, time(hours, minutes)), is_dst=False)
        return local.astimezone(pytz.UTC).replace(tzinfo=None)
