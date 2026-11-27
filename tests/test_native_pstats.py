"""Native text-stats1.10 fixtures: units, nested inclusive time and frame pairing."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path

spec=spec_from_file_location('native_stats',Path(__file__).parents[1]/'tools/native_pstats.py')
module=module_from_spec(spec);spec.loader.exec_module(module)


def test_native_hierarchical_times_are_not_added_twice():
    p=module.NativeParser()
    for line in ('Thread Main frame 20, 334.7 ms (60 Hz):','raw data:',
        ' 1.0 start Frame',' 1.3347 stop  Frame',
        '  App = 20.7 ms','    Show Code = 20.0 ms','  Draw = 313.4 ms',
        '    Set State = 200 ms','  Cull = 0.4 ms','  QA playing = 1 ',
        '  QA boss phase = 2 ','  QA clock frame = 42 '):
        assert p.feed(line) is None
    result=p.feed('Thread GPU frame 20, 4.2 ms (60 Hz):')
    assert result['root_bars_ms']=={'App':20.7,'Draw':313.4,'Cull':.4}
    assert result['inclusive_ms']['Draw:Set State']==200
    assert result['levels']=={'QA playing':1,'QA boss phase':2,'QA clock frame':42}
    assert result['events']==[[1.,'start','Frame'],[1.3347,'stop','Frame']]
    assert result['frame']==20 and p.finish()['thread']=='GPU'


def test_native_reader_ignores_server_messages_and_preserves_scientific_units():
    p=module.NativeParser()
    assert p.feed('Listening for connections.') is None
    p.feed('Thread Main frame 3, 3.1e+1 ms (30 Hz):')
    p.feed('  Draw = 1.2e-2 ms')
    p.feed('  Texture memory = 78 MB')
    row=p.finish()
    assert row['frame_ms']==31 and row['root_bars_ms']=={'Draw':.012}
    assert p.finish() is None
