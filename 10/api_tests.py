import requests

assert requests.get('http://localhost:5000/').text == '\nThis is the default response\n'
assert requests.get('http://localhost:5000/purchase_item').text == '\nMissing item\n'
assert requests.get('http://localhost:5000/purchase_item?item=sword').text == '\nBought sword\n'
assert requests.get('http://localhost:5000/purchase_item?item=knife').text == '\nBought knife\n'
assert requests.get('http://localhost:5000/purchase_item?item=shield').text == '\nInvalid item\n'
assert requests.get('http://localhost:5000/join_guild').text == '\nMissing guild ID\n'
assert requests.get('http://localhost:5000/join_guild?guild_id=1').text == '\nJoined guild 1\n'
assert requests.get('http://localhost:5000/join_guild?guild_id=a').text == '\nInvalid guild ID\n'

print('Tests passed')

