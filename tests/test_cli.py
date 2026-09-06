# Copyright 2026 Zyvor AI Labs · https://zyvor.dev
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from kubeflight.cli import main
ROOT=Path(__file__).parents[1]
def test_cli_json(tmp_path):
    out=tmp_path/'r.json'; rc=main(['check',str(ROOT/'examples/demo/app.yaml'),'--format','json','--output',str(out),'--fail-on','never'])
    assert rc==0 and '"score"' in out.read_text()
def test_cli_exit_critical():
    rc=main(['check',str(ROOT/'examples/unsafe/unsafe.yaml'),'--fail-on','critical'])
    assert rc==3
