import json
from argparse import ArgumentParser
from pathlib import Path
import os
import re
from json import dumps


def load_json(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def network_data(data, network_name):
    return next(net['network'] for net in data['networks'] if net['network']['network-id'] == network_name)

def read_elems(network):
    amps_by_uid = {}
    fibers_by_uid = {}
    fused_by_uid = {}
    roadms_by_uid = {}
    trx_by_uid = {}
    for link in network['link']:
        source = link['source']['source-node']
        trx_source = f'trx {source}'
        destination = link['destination']['dest-node']
        trx_dest = f'trx {destination}'
        elems = [elem for elem in link['te']['te-link-attributes']['OMS-attributes']['OMS-elements']]
        if source not in roadms_by_uid:
            roadms_by_uid[source] = roadm(source, to_node=elems[0]['uid'])
            # creates the corresponding transceiver end point for propagation:
            trx_by_uid[trx_source] = trx(trx_source, source)
        else:
            roadms_by_uid[source].to_node.append(elems[0]['uid'])
        if destination not in roadms_by_uid:
            roadms_by_uid[destination] = roadm(destination, from_node=elems[-1]['uid'])
            # creates the corresponding transceiver end point for propagation:
            trx_by_uid[trx_dest] = trx(trx_dest, destination)
        else:
            roadms_by_uid[destination].from_node.append(elems[-1]['uid'])
        for i, elem in enumerate(elems):
            srce = elems[i - 1]['uid'] if i > 0 else source
            dest = elems[i + 1]['uid'] if (i + 1) < len(elems) else destination
            if elem['type'] == 'Edfa':
                print(elem['uid'], srce, dest)
                amps_by_uid[elem['uid']] = amp(elem['uid'], srce, dest,
                                               type_variety=elem['element']['amplifier']['type-variety'],
                                               gain=elem['element']['amplifier']['operational']['actual-gain'],
                                               delta_p=elem['element']['amplifier']['operational']['nominal-channel-power'],
                                               tilt=elem['element']['amplifier']['operational']['tilt-target'],
                                               voa=elem['element']['amplifier']['operational']['out-voa']
                                               )
                if i == 1:
                    roadms_by_uid[source].target_pch_out = elem['element']['amplifier']['operational']['nominal-channel-power'] -\
                                                           elem['element']['amplifier']['operational']['actual-gain']
            elif elem['type'] == 'Fiber':
                fibers_by_uid[elem['uid']] = fiber(elem['uid'], srce, dest,
                                                   length=elem['element']['fiber']['length'],
                                                   loss_coef=elem['element']['fiber']['loss-coef'],
                                                   conn_in=elem['element']['fiber']['conn-in'],
                                                   conn_out=elem['element']['fiber']['conn-out'])
            elif elem['type'] == 'concentratedloss':
                fused_by_uid[elem['uid']] = fused(elem['uid'], srce, dest)

    return amps_by_uid, fibers_by_uid, roadms_by_uid, fused_by_uid, trx_by_uid

def metadata(city):
    return {'location': {
        'latitude': 0.0,
        'longitude': 0.0,
        'city': city,
        'region': ''}}

class roadm:
    def __init__(self, uid, from_node=None, to_node=None):
        self.uid = uid
        self.from_node = [] if from_node is None else [from_node]
        self.to_node = [] if to_node is None else [to_node]
        self.target_pch_out = -20   # default value if roadm is a terminal else value will be
                                    # updated using following amplifier (booster) targets
    def __repr__(self):
        return (f'uid={self.uid!r}')

    def __str__(self):
        return f'uid={self.uid!r} \n'

class trx:
    def __init__(self, uid, roadm):
        self.uid = uid
        self.from_node = roadm
        self.to_node = roadm
    def __repr__(self):
        return (f'uid={self.uid!r}')

    def __str__(self):
        return f'uid={self.uid!r} \n'

class amp:
    def __init__(self, uid, from_node, to_node, type_variety, gain, delta_p, tilt, voa):
        self.uid = uid
        self.from_node = from_node
        self.to_node = to_node
        self.type_variety = type_variety
        self.gain = gain
        self.delta_p = delta_p
        self.tilt = tilt
        self.voa = voa
    def __repr__(self):
        return (f'uid={self.uid!r}')

    def __str__(self):
        return f'uid={self.uid!r} \n'

class fiber:
    def __init__(self, uid, from_node, to_node, length, loss_coef, conn_in, conn_out):
        self.uid = uid
        self.from_node = from_node
        self.to_node = to_node
        self.length = length
        self.loss_coef = loss_coef
        self.conn_in = conn_in
        self.conn_out = conn_out
    def __repr__(self):
        return (f'uid={self.uid!r}')

    def __str__(self):
        return f'uid={self.uid!r} \n'

class fused:
    def __init__(self, uid, from_node, to_node):
        self.uid = uid
        self.from_node = from_node
        self.to_node =to_node
        self.loss = None
    def __repr__(self):
        return (f'uid={self.uid!r}')

    def __str__(self):
        return f'uid={self.uid!r} \n'

def create_gnpy_elements(amps_by_uid, roadms_by_uid, fibers_by_uid, fused_by_uid, trx_by_uid):
    # create list of elements
    elements = []

    for amp in amps_by_uid.values():
        element = {
            'uid': amp.uid,
            'type': 'Edfa',
            'type_variety': amp.type_variety,
            'operational': {
                'gain_target': amp.gain,
                'delta_p': amp.delta_p,
                'tilt_target': amp.tilt,
                'out_voa': amp.voa
                },
            'metadata': metadata(amp.uid)}
        elements.append(element)
    for roadm in roadms_by_uid.values():
        element = {
            'uid': roadm.uid,
            'type': 'Roadm',
            'params': {
                'target_pch_out_db': roadm.target_pch_out,
                'restrictions': {
                    'preamp_variety_list': [],
                    'booster_variety_list': []
                }
            },
            'metadata': metadata(roadm.uid)}
        elements.append(element)
    for trx in trx_by_uid.values():
        element = {
            'uid': trx.uid,
            'type': 'Transceiver',
            'metadata': metadata(roadm.uid)}
        elements.append(element)
    for fiber in fibers_by_uid.values():
        element = {
            'uid': fiber.uid,
            'type': 'Fiber',
            'type_variety': 'SSMF',
            'params': {
                'type_variety': 'SSMF',
                'length': fiber.length,
                'loss_coef': fiber.loss_coef,
                'length_units': 'km',
                'att_in': 0,
                'con_in': fiber.conn_in,
                'con_out': fiber.conn_out
                },
            'metadata': metadata(fiber.uid)}
        elements.append(element)
    return elements

def create_gnpy_connections(amps_by_uid, fibers_by_uid, fused_by_uid, roadms_by_uid, trx_by_uid):
    connections = []
    for amp in {**amps_by_uid, **fibers_by_uid, **fused_by_uid, **trx_by_uid}.values():
        ingress = {'from_node': amp.from_node, 'to_node': amp.uid}
        if ingress not in connections:
            connections.append(ingress)
        egress = {'from_node': amp.uid, 'to_node': amp.to_node}
        if egress not in connections:
            connections.append(egress)
    # add connection between roadm and booster and preamp
    # and raodm and trx
    for roadm in roadms_by_uid.values():
        for elem in roadm.from_node:
            ingress = {'from_node': elem, 'to_node': roadm.uid}
            if ingress not in connections:
                connections.append(ingress)
        for elem in roadm.to_node:
            egress = {'from_node': roadm.uid, 'to_node': elem}
            if egress not in connections:
                connections.append(egress)
    return connections

parser = ArgumentParser()
parser.add_argument('file', nargs='?', default='example_optical_context_reduced.json')


if __name__ == '__main__':
    args = parser.parse_args()

    localdir = Path(__file__).parent
    data = load_json(localdir / args.file)
    network = network_data(data, "single-hop-example")
    amps_by_uid, fibers_by_uid, roadms_by_uid, fused_by_uid, trx_by_uid = read_elems(network)
    data = {
        'elements': create_gnpy_elements(amps_by_uid,
                                         roadms_by_uid,
                                         fibers_by_uid,
                                         fused_by_uid,
                                         trx_by_uid),
        'connections': create_gnpy_connections(amps_by_uid, fibers_by_uid, fused_by_uid, roadms_by_uid, trx_by_uid)}
    print(data)
    with  open('test.json', 'w', encoding='utf-8') as json_file:
        json_file.write(dumps(data, indent=2, ensure_ascii=False))

    # with  open('test.txt', 'w', encoding='utf-8') as json_file:
        # json_file.write(dumps(printing, indent=2, ensure_ascii=False))
