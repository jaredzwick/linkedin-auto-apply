from os import listdir
from os.path import join
from datetime import datetime
from flask import Flask

app = Flask(__name__)


@app.route("/")
def get_count():
    todays_date = (datetime.today().strftime('%m_%d_%y'))
    onlytodayslogs = [f for f in listdir('./logs') if todays_date in f]
    str_buffer = ""
    for log in onlytodayslogs:
        str_buffer += open(f'./logs/{log}').read()
    return str(str_buffer.count('Application Submitted'))


app.run()