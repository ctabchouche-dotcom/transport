# -*- coding: utf-8 -*-
"""Disposition réelle des sièges, propre à chaque car.

Les numéros vont de l'avant vers l'arrière, de gauche à droite.
Le chauffeur est à gauche (conduite à droite). La porte est à droite.
"""

LAYOUTS = [
    ('coach_2_2_bench5', {
        'name': 'Car 2+2, banquette de 5',
        'kind': 'coach',
        'front': 'windshield',
        'label': '2+2, banquette arrière de 5',
    }),
    ('coach_door_bench5', {
        'name': 'Car, porte avant, 2+2, banquette de 5',
        'kind': 'coach',
        'front': 'windshield',
        'label': 'porte avant droite, 2+2, banquette de 5',
    }),
    ('coach_courier_2_2', {
        'name': 'Car avec siège accompagnateur, 2+2',
        'kind': 'coach',
        'front': 'windshield',
        'label': 'siège accompagnateur, puis 2+2',
    }),
    ('coach_2_2', {
        'name': 'Car 2+2 jusqu\'au fond',
        'kind': 'coach',
        'front': 'windshield',
        'label': '2+2 jusqu\'au fond',
    }),
    ('minibus_2_1_bench4', {
        'name': 'Minibus 2+1, banquette de 4',
        'kind': 'minibus',
        'front': 'sliding',
        'label': '2+1, banquette de 4',
    }),
    ('midibus_2_2_rear2', {
        'name': 'Midibus 2+2, coffre arrière',
        'kind': 'midibus',
        'front': 'windshield',
        'label': '2+2, coffre à la place des sièges arrière droit',
    }),
]

LAYOUT_BY_CODE = dict(LAYOUTS)
SEAT_LAYOUT_SELECTION = [(code, meta['name']) for code, meta in LAYOUTS]


def layout_fits(layout, capacity):
    if not capacity or capacity <= 0 or layout not in LAYOUT_BY_CODE:
        return False
    if layout == 'coach_2_2_bench5':
        return capacity > 5 and (capacity - 5) % 4 == 0
    if layout == 'coach_door_bench5':
        return capacity > 7 and (capacity - 7) % 4 == 0
    if layout == 'coach_courier_2_2':
        return capacity > 1 and (capacity - 1) % 4 == 0
    if layout == 'minibus_2_1_bench4':
        return capacity > 4 and (capacity - 4) % 3 == 0
    if layout == 'midibus_2_2_rear2':
        return capacity > 2 and (capacity - 2) % 4 == 0
    return layout == 'coach_2_2'


class _Numbers:
    def __init__(self, taken):
        self.taken = set(taken or ())
        self.n = 0

    def take(self, count):
        seats = []
        for _index in range(count):
            self.n += 1
            seats.append({'number': self.n, 'free': self.n not in self.taken})
        return seats


def _pairs(numbers, count):
    rows = []
    for _index in range(count):
        rows.append({
            'kind': 'pair',
            'left': numbers.take(2),
            'right': numbers.take(2),
        })
    return rows


def build_seat_plan(layout, capacity, taken=None):
    """Retourne le plan dessiné : avant, rangées, banquette. Exactement `capacity` sièges."""
    if not layout_fits(layout, capacity):
        layout = 'coach_2_2'
    meta = LAYOUT_BY_CODE[layout]
    numbers = _Numbers(taken)
    courier = None
    if layout == 'coach_courier_2_2':
        courier = numbers.take(1)[0]
        rows = _pairs(numbers, (capacity - 1) // 4)
    elif layout == 'coach_2_2_bench5':
        rows = _pairs(numbers, (capacity - 5) // 4)
        rows.append({'kind': 'bench', 'seats': numbers.take(5)})
    elif layout == 'coach_door_bench5':
        rows = [{'kind': 'door', 'left': numbers.take(2)}]
        rows += _pairs(numbers, (capacity - 7) // 4)
        rows.append({'kind': 'bench', 'seats': numbers.take(5)})
    elif layout == 'minibus_2_1_bench4':
        rows = []
        for _index in range((capacity - 4) // 3):
            rows.append({
                'kind': 'pair21',
                'left': numbers.take(2),
                'right': numbers.take(1),
            })
        rows.append({'kind': 'bench', 'seats': numbers.take(4)})
    elif layout == 'midibus_2_2_rear2':
        rows = _pairs(numbers, (capacity - 2) // 4)
        rows.append({'kind': 'rear2', 'left': numbers.take(2)})
    else:
        full, remainder = divmod(capacity, 4)
        rows = _pairs(numbers, full)
        if remainder:
            left_count = min(2, remainder)
            right_count = remainder - left_count
            rows.append({
                'kind': 'pair',
                'left': numbers.take(left_count) + [None] * (2 - left_count),
                'right': numbers.take(right_count) + [None] * (2 - right_count),
            })
    return {
        'kind': meta['kind'],
        'front': meta['front'],
        'label': meta['label'],
        'title': meta['label'],
        'courier': courier,
        'rows': rows,
    }


def iter_plan_seats(plan):
    if not plan:
        return
    if plan.get('courier'):
        yield plan['courier']
    for row in plan['rows']:
        for key in ('left', 'right', 'seats'):
            for seat in row.get(key) or ():
                if seat:
                    yield seat
