from kubeflight.quantities import cpu_millicores,memory_bytes,gib

def test_quantities():
    assert cpu_millicores('250m')==250
    assert cpu_millicores('2')==2000
    assert memory_bytes('1Gi')==1024**3
    assert round(gib('512Mi'),2)==0.5
