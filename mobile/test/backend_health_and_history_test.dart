import 'package:flutter_test/flutter_test.dart';
import 'package:myvoice_ai/core/errors/app_exception.dart';
import 'package:myvoice_ai/data/models/backend_config.dart';
import 'package:myvoice_ai/data/models/backend_health.dart';
import 'package:myvoice_ai/data/models/dataset_item.dart';
import 'package:myvoice_ai/data/models/generated_audio.dart';

void main() {
  test('BackendHealth parses active engine and mock flag accurately', () {
    final health = BackendHealth.fromJson({
      'status': 'ok',
      'app_name': 'MyVoice AI Backend',
      'version': '0.1.0-scaffold',
      'ffmpeg_available': true,
      'privacy_mode': 'ephemeral_stateless',
      'active_engine': {
        'id': 'mock',
        'name': 'Mock Pipeline Test Engine',
        'status': 'ready',
        'is_mock': true,
        'supports_bengali': true,
        'supports_english': true,
        'supports_style_controls': true,
        'supports_trained_checkpoints': true,
        'requires_gpu': false,
        'models': ['synthetic-tone-generator'],
        'licenses': ['MIT'],
        'notes': 'Test only',
      },
    });

    expect(health.status, 'ok');
    expect(health.ffmpegAvailable, isTrue);
    expect(health.activeEngine.id, 'mock');
    expect(health.activeEngine.isMock, isTrue);
    expect(health.activeEngine.supportsStyleControls, isTrue);
  });

  test('GeneratedAudio and DatasetRecording round-trip through DB maps', () {
    final now = DateTime(2026, 11, 26, 1, 15);
    final audio = GeneratedAudio(
      id: 'g1',
      profileId: 'p1',
      profileName: 'Me',
      text: 'Hello বাংলা',
      languageMode: 'auto',
      outputFormat: 'mp3',
      style: 'conversational',
      speed: 1.05,
      engineId: 'mock',
      isMock: true,
      filePath: '/vault/generated/g1.mp3',
      createdAt: now,
    );
    final restoredAudio = GeneratedAudio.fromDbMap(audio.toDbMap());
    expect(restoredAudio.isMock, isTrue);
    expect(restoredAudio.outputFormat, 'mp3');
    expect(restoredAudio.speed, 1.05);

    final dataset = DatasetRecording(
      id: 'd1',
      promptId: 'bn_01',
      language: 'bn',
      styleHint: 'Neutral',
      transcript: 'নমস্কার',
      filePath: '/vault/dataset/d1.wav',
      durationMs: 4200,
      createdAt: now,
    );
    final restoredDataset = DatasetRecording.fromDbMap(dataset.toDbMap());
    expect(restoredDataset.language, 'bn');
    expect(restoredDataset.durationMs, 4200);
  });

  test('BackendConfig detects plain HTTP URLs', () {
    const local = BackendConfig(baseUrl: 'http://192.168.1.50:8000');
    const tunnel = BackendConfig(baseUrl: 'https://demo.trycloudflare.com');
    expect(local.isPlainHttp, isTrue);
    expect(tunnel.isPlainHttp, isFalse);
  });

  test('BackendConfig enforces HTTPS for remote hosts and restricts HTTP to local dev opt-in', () {
    const remoteHttps = BackendConfig(baseUrl: 'https://voice.example.com');
    expect(remoteHttps.validateAndResolveUri().scheme, 'https');

    const remoteHttp = BackendConfig(baseUrl: 'http://voice.example.com', allowLocalHttpDev: true);
    expect(() => remoteHttp.validateAndResolveUri(), throwsA(isA<AppException>()));

    const localHttpDisabled = BackendConfig(baseUrl: 'http://10.0.2.2:8000', allowLocalHttpDev: false);
    expect(() => localHttpDisabled.validateAndResolveUri(), throwsA(isA<AppException>()));

    const localHttpEnabled = BackendConfig(baseUrl: 'http://10.0.2.2:8000', allowLocalHttpDev: true);
    expect(localHttpEnabled.validateAndResolveUri().host, '10.0.2.2');
  });
}
