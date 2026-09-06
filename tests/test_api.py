# Copyright 2026 Zyvor AI Labs · https://zyvor.dev
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient
from kubeflight.server import app

c=TestClient(app)
def test_health():
    r=c.get('/api/healthz'); assert r.status_code==200 and r.json()['status']=='ok'
def test_home():
    r=c.get('/'); assert r.status_code==200 and 'Know what will break' in r.text
def test_check():
    y='apiVersion: v1\nkind: ConfigMap\nmetadata: {name: x}\n'
    r=c.post('/api/check',json={'manifests':y}); assert r.status_code==200 and r.json()['resources']==1
def test_bad_yaml():
    r=c.post('/api/check',json={'manifests':'a: ['}); assert r.status_code==400
