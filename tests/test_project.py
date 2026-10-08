import cmath
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import csv
import io
import json
import math
from pathlib import Path
import shutil
import unittest
from uuid import uuid4

from edge_vibe.__main__ import compact_message, main
from edge_vibe.baseline import DEFAULT_CONFIG, operating_context, train_baseline, validate_baseline, validate_config
from edge_vibe.data import digest, load_jsonl, quality_issues, strict_json, validate_window, write_json, write_jsonl
from edge_vibe.demo import make_window, monitoring_windows, reference_windows
from edge_vibe.dsp import axis_features, extract_features, fft
from edge_vibe.monitor import Monitor, replay, summarize
from edge_vibe.outbox import Outbox, validate_message
from edge_vibe.report import csv_text, export_csv, render_report


class WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.scratch_root = Path('.test-work').resolve()
        self.scratch_root.mkdir(exist_ok=True)
        self.folder = self.scratch_root / str(uuid4())
        self.folder.mkdir()

    def tearDown(self):
        if self.folder.resolve().parent != self.scratch_root or self.folder.is_symlink():
            raise RuntimeError('Unexpected test cleanup path')
        shutil.rmtree(self.folder)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()


class SignalTests(unittest.TestCase):
    def test_fft_impulse(self):
        self.assertEqual(fft([1, 0, 0, 0, 0, 0, 0, 0]), [1 + 0j] * 8)

    def test_fft_matches_independent_dft(self):
        values = [0.3, -1.2, 2.5, 0.7, -0.4, 0.1, 0.8, -0.6]
        actual = fft(values)
        expected = [sum(v * cmath.exp(-2j * math.pi * k * n / 8) for n, v in enumerate(values)) for k in range(8)]
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a.real, e.real, places=12)
            self.assertAlmostEqual(a.imag, e.imag, places=12)

    def test_fft_rejects_non_power_two(self):
        for values in ([], [1, 2, 3]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                fft(values)

    def test_sine_analytic_rms_peak_and_amplitude(self):
        samples = [2 + .4 * math.sin(2 * math.pi * 64 * i / 1024) for i in range(1024)]
        f = axis_features(samples, 1024, 10, 400)
        self.assertAlmostEqual(f['mean_g'], 2)
        self.assertAlmostEqual(f['rms_g'], .4 / math.sqrt(2), places=12)
        self.assertAlmostEqual(f['peak_g'], .4, places=12)
        self.assertAlmostEqual(f['crest_factor'], math.sqrt(2), places=12)
        self.assertEqual(f['dominant_hz'], 64)
        self.assertAlmostEqual(f['dominant_amplitude_g_peak'], .4, places=12)

    def test_band_energy_two_tones(self):
        samples = [.3 * math.sin(2 * math.pi * 50 * i / 1024) + .4 * math.sin(2 * math.pi * 250 * i / 1024) for i in range(1024)]
        self.assertAlmostEqual(axis_features(samples, 1024, 10, 400)['band_rms_g'], math.sqrt((.3**2 + .4**2)/2), places=12)
        self.assertAlmostEqual(axis_features(samples, 1024, 40, 60)['band_rms_g'], .3 / math.sqrt(2), places=12)

    def test_psd_parseval_window_energy(self):
        samples = [.1 * math.sin(i * .32) + .02 * math.cos(i * .71) for i in range(256)]
        mean = sum(samples) / len(samples)
        weights = [.5 - .5 * math.cos(2 * math.pi * i / 256) for i in range(256)]
        expected = math.sqrt(sum(((v-mean)*w)**2 for v, w in zip(samples, weights)) / sum(w*w for w in weights))
        self.assertAlmostEqual(axis_features(samples, 1024, 0, 512)['band_rms_g'], expected, places=12)

    def test_nyquist_amplitude_not_doubled(self):
        samples = [.2 * (-1)**i for i in range(256)]
        self.assertAlmostEqual(axis_features(samples, 1024, 400, 512)['spectrum']['amplitude_g_peak'][-1], .2, places=12)

    def test_static_gravity_removed(self):
        f = axis_features([1.0]*1024, 1024, 10, 400)
        self.assertEqual(f['rms_g'], 0)
        self.assertEqual(f['peak_g'], 0)
        self.assertIsNone(f['crest_factor'])
        self.assertIsNone(f['dominant_hz'])
        self.assertEqual(f['band_rms_g'], 0)

    def test_vector_rms_is_three_axis_energy(self):
        w = make_window(1)
        f = extract_features(w, DEFAULT_CONFIG)
        expected = .075 * math.sqrt((1 + .2**2 + .005**2 + .6**2 + .25**2)/2)
        self.assertAlmostEqual(f['vector_rms_g'], expected, places=12)
        self.assertEqual(f['frequency_resolution_hz'], 1)

    def test_nyquist_band_guard(self):
        w = make_window(1)
        w['sample_rate_hz'] = 512
        with self.assertRaisesRegex(ValueError, 'Nyquist'):
            extract_features(w, DEFAULT_CONFIG)

    def test_empty_band_guard(self):
        with self.assertRaisesRegex(ValueError, 'no FFT bins'):
            axis_features([0]*64, 1024, 1, 2)


class InputTests(WorkspaceCase):
    def test_finite_values_required(self):
        for value in (float('nan'), float('inf'), True, '1'):
            w = make_window(1)
            w['acceleration_g']['x'][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_window(w)

    def test_equal_power_two_lengths(self):
        for size in (0, 32, 100, 16384):
            w = make_window(1)
            w['acceleration_g'] = {a: [0]*size for a in ('x', 'y', 'z')}
            with self.subTest(size=size), self.assertRaises(ValueError):
                validate_window(w)
        w = make_window(1)
        w['acceleration_g']['z'].pop()
        with self.assertRaises(ValueError):
            validate_window(w)

    def test_missing_axis_rejected(self):
        w = make_window(1)
        del w['acceleration_g']['y']
        with self.assertRaises(ValueError):
            validate_window(w)

    def test_timezone_required(self):
        w = make_window(1)
        w['observed_at'] = '2026-10-03T09:00:00'
        with self.assertRaisesRegex(ValueError, 'timezone'):
            validate_window(w)

    def test_metadata_bounds(self):
        for key, value in (('sample_rate_hz', 0), ('sample_rate_hz', 100001), ('rpm', -1), ('load_pct', 101), ('schema_version', True), ('approved_reference', 1)):
            w = make_window(1)
            w[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_window(w)

    def test_actuator_phase_required(self):
        with self.assertRaises(ValueError):
            validate_window(make_window(1, state='actuating'))

    def test_quality_flags_and_range(self):
        w = make_window(1)
        w['quality'] = {'missing_samples': 2, 'clipped': True, 'timing_valid': False}
        w['acceleration_g']['x'][0] = w['sensor']['range_g']
        self.assertEqual(len(quality_issues(w)), 4)
        w['quality']['missing_samples'] = True
        with self.assertRaises(ValueError):
            validate_window(w)

    def test_strict_json(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                strict_json(raw)

    def test_jsonl_bom_blank_and_duplicate(self):
        path = self.folder / 'records.jsonl'
        path.write_text('\ufeff\n' + json.dumps(make_window(1)) + '\n\n', encoding='utf-8')
        self.assertEqual(len(load_jsonl(path, validate_window)), 1)
        write_jsonl([make_window(1), make_window(1)], path)
        with self.assertRaisesRegex(ValueError, 'Line 2.*Duplicate'):
            load_jsonl(path, validate_window)

    def test_config_rejects_invalid_hysteresis_or_types(self):
        for key, value in (('enter_windows', True), ('min_reference_windows', 0), ('rms_clear_multiplier', 2), ('temperature_clear_c', 80), ('band_low_hz', 500), ('load_bin_width', 0), ('max_gap_seconds', float('nan'))):
            config = deepcopy(DEFAULT_CONFIG)
            config[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config(config)
        with self.assertRaises(ValueError):
            validate_config({})


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = train_baseline(reference_windows())

    def test_only_approved_quality_references(self):
        self.assertEqual(len(self.model['groups']), 3)
        self.assertEqual(sum(g['ready'] for g in self.model['groups'].values()), 2)
        self.assertEqual(set(self.model['excluded_reference_ids']), {'reference-not-approved', 'reference-invalid'})

    def test_structural_fields_are_validated(self):
        def resigned(mutate):
            model = deepcopy(self.model)
            mutate(model)
            model['model_sha256'] = digest({k: v for k, v in model.items() if k != 'model_sha256'})
            return model
        validate_baseline(resigned(lambda m: None))
        ready = next(k for k, g in self.model['groups'].items() if g['ready'])
        for mutate in (
            lambda m: m.update(created_at='2026-10-03T09:00:00'),
            lambda m: m.update(created_at=5),
            lambda m: m.update(excluded_reference_ids='oops'),
            lambda m: m.update(excluded_reference_ids=[1]),
            lambda m: m['groups'][ready].update(reference_ids=m['groups'][ready]['reference_ids'][:-1] * 2 if False else [m['groups'][ready]['reference_ids'][0]] * m['groups'][ready]['reference_count']),
            lambda m: m['groups'][ready].update(median_vector_rms_g=-0.1),
            lambda m: m['groups'][ready].update(mad_vector_rms_g=float('nan')),
            lambda m: m['groups'][ready].pop('context'),
        ):
            with self.assertRaises((ValueError, KeyError, TypeError)):
                validate_baseline(resigned(mutate))

    def test_fewer_than_minimum_is_not_ready(self):
        group = next(g for g in self.model['groups'].values() if g['context']['cycle_phase'] == 'retract')
        self.assertFalse(group['ready'])
        self.assertEqual(group['reference_count'], 3)

    def test_nominal_analytic_threshold(self):
        group = next(g for g in self.model['groups'].values() if g['context']['operating_state'] == 'steady')
        center = .075 * math.sqrt((1+.2**2+.005**2+.6**2+.25**2)/2)
        self.assertAlmostEqual(group['median_vector_rms_g'], center, places=12)
        self.assertAlmostEqual(group['enter_rms_g'], center*2, places=12)
        self.assertAlmostEqual(group['clear_rms_g'], center*1.4, places=12)

    def test_context_separates_mount_speed_load_provenance(self):
        w = make_window(1)
        original = digest(operating_context(w, DEFAULT_CONFIG))
        variants = []
        for key, value in (('rpm', 2100), ('load_pct', 85), ('provenance', 'hardware')):
            variant = deepcopy(w)
            variant[key] = value
            variants.append(variant)
        variant = deepcopy(w)
        variant['sensor']['mount_id'] = 'new-mount'
        variants.append(variant)
        for variant in variants:
            self.assertNotEqual(digest(operating_context(variant, DEFAULT_CONFIG)), original)

    def test_context_copy_does_not_alias_sensor(self):
        w = make_window(1)
        context = operating_context(w, DEFAULT_CONFIG)
        w['sensor']['mount_id'] = 'changed'
        self.assertNotEqual(w['sensor']['mount_id'], context['sensor']['mount_id'])

    def test_missing_context_and_transient_training_excluded(self):
        records = [make_window(1, state='startup', approved=True), make_window(2, rpm=None, approved=True)]
        model = train_baseline(records)
        self.assertFalse(model['groups'])
        self.assertEqual(len(model['excluded_reference_ids']), 2)

    def test_model_digest_tampering_rejected(self):
        model = deepcopy(self.model)
        model['config']['enter_windows'] = 1
        with self.assertRaisesRegex(ValueError, 'digest'):
            validate_baseline(model)

    def test_duplicate_reference_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            train_baseline([make_window(1, approved=True)]*2)

    def test_zero_reference_hysteresis_floor(self):
        windows = [make_window(i, amplitude=0, approved=True) for i in range(5)]
        group = next(iter(train_baseline(windows)['groups'].values()))
        self.assertEqual(group['enter_rms_g'], .03)
        self.assertAlmostEqual(group['clear_rms_g'], .024)


class MonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = train_baseline(reference_windows())

    def test_demo_expected_transitions(self):
        records, events = replay(monitoring_windows(), self.model)
        self.assertEqual([(e['transition'], e['evidence'][-1]['window_id']) for e in events], [('raised', 'window-072'), ('cleared', 'window-077'), ('raised', 'window-080'), ('cleared', 'window-083')])
        self.assertEqual([len(e['evidence']) for e in events], [3, 2, 3, 2])
        self.assertEqual(summarize(records, events)['final_alarm_active'], False)

    def test_three_windows_required(self):
        records, events = replay([make_window(i, amplitude=.3) for i in range(10, 13)], self.model)
        self.assertEqual([r['assessment'] for r in records], ['PENDING', 'PENDING', 'ALARM'])
        self.assertEqual(len(events), 1)

    def test_invalid_window_interrupts_raise_streak(self):
        windows = [make_window(i, amplitude=.3) for i in range(10, 15)]
        windows[2]['quality']['timing_valid'] = False
        records, events = replay(windows, self.model)
        self.assertEqual(records[-1]['assessment'], 'PENDING')
        self.assertFalse(events)

    def test_gap_interrupts_raise_streak(self):
        records, events = replay([make_window(i, amplitude=.3) for i in (10, 11, 20)], self.model)
        self.assertEqual(records[-1]['assessment'], 'PENDING')
        self.assertFalse(events)

    def test_context_switch_interrupts_raise_streak(self):
        windows = [make_window(10, amplitude=.3), make_window(11, amplitude=.3), make_window(12, rpm=2100), make_window(13, amplitude=.3)]
        records, events = replay(windows, self.model)
        self.assertEqual(records[-1]['assessment'], 'PENDING')
        self.assertFalse(events)

    def test_invalid_stopped_unknown_do_not_clear_latched_alarm(self):
        windows = [make_window(i, amplitude=.3) for i in range(10, 13)]
        invalid = make_window(13)
        invalid['quality']['clipped'] = True
        windows += [invalid, make_window(14, state='stopped'), make_window(15, rpm=2100)]
        records, events = replay(windows, self.model)
        self.assertTrue(all(r['alarm_active'] for r in records[2:]))
        self.assertEqual(len(events), 1)

    def test_normal_other_context_keeps_original_alarm(self):
        windows = [make_window(i, amplitude=.3) for i in range(10, 13)]
        windows.append(make_window(13, state='actuating', phase='extend', rpm=None, amplitude=.11))
        records, _ = replay(windows, self.model)
        self.assertEqual(records[-1]['assessment'], 'NORMAL_WINDOW')
        self.assertTrue(records[-1]['alarm_active'])

    def test_recovery_requires_two_lower_windows(self):
        windows = [make_window(i, amplitude=.3) for i in range(10, 13)] + [make_window(13), make_window(14)]
        records, events = replay(windows, self.model)
        self.assertEqual(records[-2]['assessment'], 'CLEAR_PENDING')
        self.assertFalse(records[-1]['alarm_active'])
        self.assertEqual(events[-1]['transition'], 'cleared')

    def test_hysteresis_zone_does_not_clear(self):
        windows = [make_window(i, amplitude=.3) for i in range(10, 13)] + [make_window(i, amplitude=.12) for i in range(13, 16)]
        records, events = replay(windows, self.model)
        self.assertTrue(records[-1]['alarm_active'])
        self.assertEqual(len(events), 1)

    def test_temperature_raise_and_recovery(self):
        windows = [make_window(i, temperature=85) for i in range(10, 13)] + [make_window(13, temperature=76), make_window(14, temperature=74), make_window(15, temperature=73)]
        records, events = replay(windows, self.model)
        self.assertEqual(records[3]['assessment'], 'ALARM')
        self.assertIn('Housing temperature', events[0]['reasons'][0])
        self.assertFalse(records[-1]['alarm_active'])

    def test_duplicate_and_out_of_order(self):
        for next_window in (make_window(10), make_window(9)):
            monitor = Monitor(self.model)
            monitor.process(make_window(10))
            with self.assertRaises(ValueError):
                monitor.process(next_window)

    def test_baseline_stays_frozen_and_copied(self):
        model = deepcopy(self.model)
        monitor = Monitor(model)
        before = digest(monitor.model)
        model['config']['enter_windows'] = 1
        for i in range(10, 13):
            monitor.process(make_window(i, amplitude=.3))
        self.assertEqual(digest(monitor.model), before)

    def test_summary_retains_alarm_on_other_stream(self):
        records = [{'device_id':'a', 'asset_id':'motor', 'assessment':'ALARM', 'alarm_active':True}, {'device_id':'b', 'asset_id':'motor', 'assessment':'NORMAL_WINDOW', 'alarm_active':False}]
        self.assertTrue(summarize(records, [])['final_alarm_active'])
        self.assertIsNone(summarize([], [])['final_alarm_active'])


class OutboxTests(WorkspaceCase):
    @classmethod
    def setUpClass(cls):
        model = train_baseline(reference_windows())
        records, events = replay([make_window(i, amplitude=.3) for i in range(10, 13)], model)
        cls.messages = [compact_message(r) for r in records + events]

    def test_compact_summaries_remove_spectrum(self):
        self.assertNotIn('spectrum', self.messages[0]['features']['axes']['x'])
        self.assertNotIn('acceleration_g', self.messages[0])
        self.assertEqual(len(self.messages[-1]['evidence']), 3)

    def test_persists_restart_and_deduplicates(self):
        db = self.folder / 'queue.sqlite'
        with Outbox(db) as queue:
            self.assertEqual(queue.enqueue(self.messages), 4)
            self.assertEqual(queue.enqueue(self.messages), 0)
        with Outbox(db) as queue:
            self.assertEqual(queue.status(), {'total':4, 'pending':4, 'acknowledged':0})

    def test_prune_removes_only_acknowledged_messages(self):
        db = self.folder / 'queue.sqlite'
        with Outbox(db) as queue:
            queue.enqueue(self.messages)
            self.assertEqual(queue.prune(), 0)
            batch = queue.export_batch(2)
            queue.acknowledge(batch)
            self.assertEqual(queue.status(), {'total': 4, 'pending': 2, 'acknowledged': 2})
            self.assertEqual(queue.prune(keep_acknowledged=1), 1)
            self.assertEqual(queue.status(), {'total': 3, 'pending': 2, 'acknowledged': 1})
            kept = queue.connection.execute('SELECT record_id FROM messages WHERE acknowledged=1').fetchall()
            self.assertEqual(kept, [(batch['messages'][1]['record_id'],)])
            self.assertEqual(queue.prune(), 1)
            self.assertEqual(queue.status(), {'total': 2, 'pending': 2, 'acknowledged': 0})
            # Pending messages survive, and a pruned record can be re-queued (local dedupe only).
            self.assertEqual(len(queue.export_batch()['messages']), 2)
            self.assertEqual(queue.enqueue(self.messages), 2)
            with self.assertRaises(ValueError):
                queue.prune(-1)

    def test_conflict_rolls_back_whole_enqueue(self):
        with Outbox(self.folder / 'queue.sqlite') as queue:
            queue.enqueue(self.messages[:1])
            conflict = deepcopy(self.messages[0])
            conflict['provenance'] = 'changed'
            with self.assertRaisesRegex(ValueError, 'different payload'):
                queue.enqueue([self.messages[1], conflict])
            self.assertEqual(queue.status()['total'], 1)

    def test_export_does_not_ack_and_retains_order(self):
        with Outbox(self.folder / 'queue.sqlite') as queue:
            queue.enqueue(self.messages)
            batch = queue.export_batch(2)
            self.assertEqual([r['record_id'] for r in batch['messages']], [r['record_id'] for r in self.messages[:2]])
            self.assertEqual(queue.status()['pending'], 4)
            self.assertEqual(queue.export_batch(2)['messages'], batch['messages'])

    def test_ack_idempotent_and_omits_acked(self):
        with Outbox(self.folder / 'queue.sqlite') as queue:
            queue.enqueue(self.messages)
            batch = queue.export_batch(2)
            self.assertEqual(queue.acknowledge(batch), 2)
            self.assertEqual(queue.acknowledge(batch), 0)
            self.assertEqual(len(queue.export_batch()['messages']), 2)

    def test_tampered_ack_rolls_back(self):
        with Outbox(self.folder / 'queue.sqlite') as queue:
            queue.enqueue(self.messages)
            batch = queue.export_batch()
            batch['messages'][1]['payload']['provenance'] = 'tampered'
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                queue.acknowledge(batch)
            self.assertEqual(queue.status()['acknowledged'], 0)

    def test_unknown_ack_rolls_back(self):
        with Outbox(self.folder / 'queue.sqlite') as queue:
            queue.enqueue(self.messages[:1])
            batch = queue.export_batch()
            batch['messages'].append({'record_id':self.messages[1]['record_id'], 'payload_sha256':digest(self.messages[1]), 'payload':self.messages[1]})
            with self.assertRaisesRegex(ValueError, 'queued message'):
                queue.acknowledge(batch)
            self.assertEqual(queue.status()['acknowledged'], 0)

    def test_duplicate_receipt_rolls_back(self):
        with Outbox(self.folder / 'queue.sqlite') as queue:
            queue.enqueue(self.messages[:1])
            batch = queue.export_batch()
            batch['messages'] *= 2
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                queue.acknowledge(batch)
            self.assertEqual(queue.status()['acknowledged'], 0)

    def test_export_bounds(self):
        with Outbox(self.folder / 'queue.sqlite') as queue:
            for limit in (0, 10001, True):
                with self.subTest(limit=limit), self.assertRaises(ValueError):
                    queue.export_batch(limit)

    def test_raw_waveform_and_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            validate_message(make_window(1))
        record = deepcopy(self.messages[0])
        record['features']['vector_rms_g'] = float('inf')
        with self.assertRaises(ValueError):
            validate_message(record)


class SummaryTests(unittest.TestCase):
    def test_final_alarm_reported_per_stream(self):
        def second_asset(window):
            window['asset_id'] = 'DEMO-MOTOR-02'
            return window
        references = reference_windows() + [second_asset(w) for w in reference_windows()]
        model = train_baseline(references)
        healthy = [make_window(i) for i in range(1, 4)]
        other = [second_asset(make_window(i, amplitude=0.3)) for i in range(10, 14)]
        assessments, events = replay(healthy + other, model)
        summary = summarize(assessments, events)
        self.assertEqual(summary['final_alarm_by_stream'],
                         {'SIM-NODE-01/DEMO-MOTOR-01': False, 'SIM-NODE-01/DEMO-MOTOR-02': True})
        self.assertTrue(summary['final_alarm_active'])
        self.assertEqual(summarize([], [])['final_alarm_by_stream'], {})


class WorkflowTests(WorkspaceCase):
    @classmethod
    def setUpClass(cls):
        cls.model = train_baseline(reference_windows())

    def test_demo_end_to_end(self):
        code, out, err = self.cli('demo', '--output', self.folder / 'demo')
        self.assertEqual((code, err), (0, ''))
        result = json.loads(out)
        self.assertEqual((result['windows'], result['events_raised'], result['events_cleared']), (28, 2, 2))
        self.assertEqual(result['queue'], {'added':32, 'duplicate_added':0, 'demo_acknowledged':10, 'total':32, 'pending':22, 'acknowledged':10})
        self.assertTrue((self.folder / 'demo' / 'report.html').is_file())

    def test_train_features_analyze_report(self):
        refs, windows, model = self.folder/'refs.jsonl', self.folder/'raw.jsonl', self.folder/'model.json'
        write_jsonl(reference_windows(), refs)
        write_jsonl([make_window(60)], windows)
        commands = [('train', refs, '--output', model), ('features', windows, '--output', self.folder/'features.jsonl'), ('analyze', windows, '--baseline', model, '--output', self.folder/'analysis'), ('report', windows, '--baseline', model, '--output', self.folder/'report.html')]
        for command in commands:
            code, _, err = self.cli(*command)
            self.assertEqual((code, err), (0, ''))
        self.assertEqual(len(load_jsonl(self.folder/'features.jsonl')), 1)

    def test_active_alarm_exit_code(self):
        raw, baseline = self.folder/'raw.jsonl', self.folder/'baseline.json'
        write_jsonl([make_window(i, amplitude=.3) for i in range(10, 13)], raw)
        write_json(self.model, baseline)
        code, out, err = self.cli('analyze', raw, '--baseline', baseline, '--output', self.folder/'analysis')
        self.assertEqual((code, err), (1, ''))
        self.assertTrue(json.loads(out)['final_alarm_active'])
        self.assertTrue((self.folder/'analysis'/'report.html').is_file())

    def test_input_overwrite_protected(self):
        raw = self.folder/'raw.jsonl'
        write_jsonl([make_window(1)], raw)
        before = raw.read_bytes()
        code, _, err = self.cli('features', raw, '--output', raw)
        self.assertEqual(code, 2)
        self.assertIn('overwrite inputs', err)
        self.assertEqual(raw.read_bytes(), before)

    def test_analysis_baseline_collision_protected(self):
        raw, baseline = self.folder/'raw.jsonl', self.folder/'baseline.json'
        write_jsonl([make_window(1)], raw)
        write_json(self.model, baseline)
        code, _, err = self.cli('analyze', raw, '--baseline', baseline, '--output', self.folder)
        self.assertEqual(code, 2)
        self.assertIn('overwrite inputs', err)

    def test_outbox_cli_roundtrip(self):
        raw, db, batch = self.folder/'messages.jsonl', self.folder/'queue.sqlite', self.folder/'batch.json'
        records, _ = replay([make_window(1)], self.model)
        write_jsonl(records, raw)
        for args in (('outbox','enqueue',raw,'--db',db), ('outbox','export','--db',db,'--output',batch), ('outbox','ack',batch,'--db',db)):
            code, _, err = self.cli(*args)
            self.assertEqual((code, err), (0, ''))
        code, out, err = self.cli('outbox', 'status', '--db', db)
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out)['pending'], 0)
        code, out, err = self.cli('outbox', 'prune', '--db', db)
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out), {'deleted': 1, 'total': 0, 'pending': 0, 'acknowledged': 0})

    def test_missing_database_is_not_created(self):
        path = self.folder/'missing.sqlite'
        code, _, err = self.cli('outbox', 'status', '--db', path)
        self.assertEqual(code, 2)
        self.assertIn('does not exist', err)
        self.assertFalse(path.exists())

    def test_bad_json_has_line_error_no_traceback(self):
        raw = self.folder/'bad.jsonl'
        raw.write_text('{broken}\n', encoding='utf-8')
        code, _, err = self.cli('features', raw, '--output', self.folder/'out.jsonl')
        self.assertEqual(code, 2)
        self.assertIn('Line 1', err)
        self.assertNotIn('Traceback', err)

    def test_html_embedded_data_escapes_script_injection(self):
        window = make_window(1)
        window['window_id'] = '</script><script>alert(1)</script>'
        records, events = replay([window], self.model)
        html = render_report([window], records, events, self.model, self.folder/'report.html').read_text(encoding='utf-8')
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertIn('\\u003c/script>', html)
        self.assertNotIn('/*MONITOR_DATA*/null', html)

    def test_report_rejects_wrong_waveform(self):
        window = make_window(1)
        records, events = replay([window], self.model)
        window['temperature_c'] = 60
        with self.assertRaisesRegex(ValueError, 'does not match'):
            render_report([window], records, events, self.model, self.folder/'report.html')

    def test_csv_formula_neutralization(self):
        for value in ('=SUM(A1)', ' +1', '-cmd', '@func'):
            self.assertTrue(csv_text(value).startswith("'"))
        records, _ = replay([make_window(1, identifier='=danger')], self.model)
        path = self.folder/'measurements.csv'
        export_csv(records, path)
        with path.open(newline='', encoding='utf-8') as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row['window_id'], "'=danger")


if __name__ == '__main__':
    unittest.main()
