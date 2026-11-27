"""Compare native submitted poses with independent logical contact activation."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import pytest

spec=spec_from_file_location('attack_sync',Path(__file__).parents[1]/'tools/verify_attack_sync.py')
module=module_from_spec(spec);spec.loader.exec_module(module)
CASES=list(module.cases())


@pytest.mark.parametrize('profile,phase,definition',CASES,
    ids=[f'{p.id}-phase{phase}-{attack.kind.value}' for p,phase,attack in CASES])
def test_boss_visible_strike_is_within_two_steps_of_contact_activation(profile,phase,definition):
    result=module.measure(profile,phase,definition)
    assert result['passed'],result
