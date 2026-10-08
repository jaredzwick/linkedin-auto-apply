import requests, json
url = "http://127.0.0.1:4444"
r = requests.get("{}/status".format(url))
data = json.loads(r.text)
for node in data['value']['nodes']:
    for slot in node['slots']:
        if slot['session']:
            id = slot['session']['sessionId']
            r = requests.delete("{}/session/{}".format(url, id))
