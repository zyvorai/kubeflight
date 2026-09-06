from kubeflight.parser import parse_text, resource_key, ManifestError
import pytest

def test_multi_doc_and_list():
    items=parse_text('''apiVersion: v1\nkind: ConfigMap\nmetadata: {name: a}\n---\napiVersion: v1\nkind: List\nitems:\n- apiVersion: v1\n  kind: Service\n  metadata: {name: s}\n''')
    assert len(items)==2
    assert resource_key(items[0])=='ConfigMap/default/a'

def test_invalid_yaml():
    with pytest.raises(ManifestError): parse_text('a: [')
