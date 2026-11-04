import json
import os
import pathlib
import urllib.parse
import urllib.request

PARTS = {
    'MK1F4LL/A': 'Night Sky 256GB',
    'MK1E4LL/A': 'Star White 256GB',
    'MK1H4LL/A': 'Night Sky 512GB',
    'MK1G4LL/A': 'Star White 512GB',
    'MK1L4LL/A': 'Night Sky 1TB',
    'MK1J4LL/A': 'Star White 1TB',
    'MK1R4LL/A': 'Night Sky 2TB',
    'MK1Q4LL/A': 'Star White 2TB',
}
# Only Menlo Park is verified in the user's requested area so far.
STORES = {'R067': 'Apple Menlo Park'}
STATE = pathlib.Path('stock_state.json')


def fetch():
    params = [('pl', 'true'), ('location', '08854')]
    params += [(f'parts.{i}', part) for i, part in enumerate(PARTS)]
    url = 'https://www.apple.com/shop/retail/pickup-message?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def notify(topic, store, label):
    body = f'iPhone Duo {label} is available for pickup at {store}. Confirm on Apple before traveling.'
    req = urllib.request.Request(
        f'https://ntfy.sh/{urllib.parse.quote(topic, safe="")}',
        data=body.encode('utf-8'),
        headers={'Title': 'iPhone Duo pickup available', 'Priority': 'high', 'Click': 'https://www.apple.com/shop/buy-iphone'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status not in (200, 201, 202):
            raise RuntimeError(f'ntfy returned HTTP {response.status}')


def main():
    topic = os.environ.get('NTFY_TOPIC', '').strip()
    if not topic:
        raise RuntimeError('Missing NTFY_TOPIC secret')
    data = fetch()
    stores = {s.get('storeNumber'): s for s in data.get('body', {}).get('stores', [])}
    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    current = {}
    alerts = []
    for store_id, name in STORES.items():
        store = stores.get(store_id)
        if not store:
            raise RuntimeError(f'Missing store {store_id}; refusing to update state')
        inventory = store.get('partsAvailability', {})
        for part, label in PARTS.items():
            item = inventory.get(part)
            if not isinstance(item, dict):
                raise RuntimeError(f'Missing inventory record for {store_id} {part}')
            title = item.get('messageTypes', {}).get('regular', {}).get('storePickupProductTitle', '')
            if 'iPhone Duo' not in title:
                raise RuntimeError(f'Unexpected product title for {part}: {title!r}')
            status = item.get('pickupDisplay')
            if status not in ('available', 'unavailable', 'ineligible'):
                raise RuntimeError(f'Unknown pickup status {status!r} for {part}')
            key = f'{store_id}:{part}'
            current[key] = status == 'available'
            print(f'{name} | {label}: {status}')
            if current[key] and not old.get(key, False):
                alerts.append((name, label))
    # Send before saving state; if push fails, retry next run.
    for name, label in alerts:
        notify(topic, name, label)
        print(f'ALERT SENT: {name} {label}')
    STATE.write_text(json.dumps(current, indent=2) + '\n')
    print(f'Check complete. {len(alerts)} new availability alert(s).')


if __name__ == '__main__':
    main()
