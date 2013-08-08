"""
Flask server to accept data from android phones
"""

import json
from flask import Flask, request, g

app = Flask(__name__, static_folder='static', static_url_path='/static')

from datastore import Datastore
from particle_filter import ParticleFilter
from wifi_magic import WifiMagic
from wifi_deeper_magic import WifiDeeperMagic
from sensors_magic import SensorsMagic
from random import sample, random
from werkzeug.contrib.cache import SimpleCache
cache = SimpleCache()

### Server Pages ###

@app.route("/")
def hello():
    handle = open('static/marauders_map.html','r')
    html = handle.read()
    handle.close()
    return html

@app.route("/push", methods=['GET','POST'])
def data():
    if 'data' not in request.form:
        return 'Nothing received'
        # Test code:
        # request.form = {'data' : json.dumps([
        #         {'name' : 'sensors',
        #          'data' : 'shit'},
        #         {'name' : 'wifi',
        #          'data' : [{'label' : 'blah',
        #                     'estimatedDistance' : 10}]}])}
    data = json.loads(request.form['data'])

    wifi_magic = WifiMagic()

    walls = get_db('walls')

    if SensorsMagic.USE_WALLS and  not walls:
        with open('walls/walls.txt', 'r') as json_walls:
            walls = json.load(json_walls)
        set_db('walls', frozenset([tuple(point) for point in walls]))
    sensors_magic = SensorsMagic(walls)
    wifi_deep_magic = WifiDeeperMagic(cache)


    saved_particles = get_db("particles")
    pf = ParticleFilter(particles=saved_particles)


    for d in data:
        if d['name'] == 'sensors':
            result = sensors_magic.parse(d['data'])
            sensors_magic.update_particles(pf.get_particles(), result)
        if d['name'] == 'wifi':
            wifidata = d['data']
            corr = wifi_deep_magic.get_corrections()
            for r in wifidata:
                if r['label'] in corr:
                    oldLvl = r['level']
                    r['level']+=corr[r['label']]
                    print "corrected",r['label'],'from',oldLvl,'to',r['level']
            result = wifi_magic.parse(wifidata)
            set_db("router_dist", result)
            result = wifi_magic.update_particles(pf.get_particles(), result)
    
    
    pf.resample();
    set_db("particles", pf.get_particles())
    print "Particles updated to", pf.get_position(), " (var:", pf.get_std(),")"
    return 'Saved..'

@app.route("/get")
def get():
    saved_particles = get_db("particles")
    pf = ParticleFilter(particles=saved_particles)
    return 'mean: '+ str(pf.get_position()) + ', std: ' +str(pf.get_std())

@app.route("/get_system_state")
def get_system_state():
    return json.dumps({
                        'particles' : sample_particles(),
                        'router_distances' : get_router_dist()
                      })

@app.route("/update_base_level", methods=['GET','POST'])
def update_base_level():
    if 'data' not in request.form:
        return 'Nothing received'
    data = json.loads(request.form['data'])
    wdm = WifiDeeperMagic(cache)
    wdm.store_base_level(data['name'],data['base_level'])
    return "thank you"


def sample_particles():
    saved_particles = get_db("particles")
    if saved_particles:
        samples = [particle['position'] for particle in sample(saved_particles,300)]
    else:
        samples = []
    return samples

@app.route("/check_persistance")
def check_persistance():
    old_shit = get_db("particles")
    print 'old particles:'
    print old_shit
    rand_shit = random()
    print 'going to add: %f' % rand_shit
    save_db(rand_shit)
    return json.dumps((old_shit, rand_shit))

def get_db(name):
    return cache.get(name)

def set_db(name, data):
    cache.set(name, data)
    
@app.route("/router_info")
def send_router_info():
    routers = WifiMagic.ROUTER_POS
    return json.dumps(routers)

def get_router_dist():
    distsM = get_db('router_dist')
    distsM = distsM if distsM else []
    distsPX = [ (d[0],d[1]*WifiMagic.PIXELS_PER_METER) for d in distsM ]
        
    return distsPX

if __name__ == "__main__":
    app.debug = True
    app.run(host='0.0.0.0', port=80)
