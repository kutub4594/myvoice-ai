import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:myvoice_ai/data/models/backend_config.dart';
import 'package:myvoice_ai/data/models/backend_health.dart';
import 'package:myvoice_ai/data/models/dataset_item.dart';
import 'package:myvoice_ai/data/models/generated_audio.dart';
import 'package:myvoice_ai/data/models/voice_profile.dart';
import 'package:myvoice_ai/data/services/api_client_service.dart';
import 'package:myvoice_ai/data/services/audio_player_service.dart';
import 'package:myvoice_ai/data/services/audio_recorder_service.dart';
import 'package:myvoice_ai/data/services/dataset_export_service.dart';
import 'package:myvoice_ai/data/services/export_service.dart';
import 'package:myvoice_ai/data/services/local_storage_service.dart';
import 'package:uuid/uuid.dart';

final localStorageProvider = Provider<LocalStorageService>((ref) {
  return LocalStorageService();
});

final apiClientProvider = Provider<ApiClientService>((ref) {
  return ApiClientService();
});

final audioRecorderProvider = Provider<AudioRecorderService>((ref) {
  final recorder = AudioRecorderService();
  ref.onDispose(recorder.dispose);
  return recorder;
});

final audioPlayerProvider = ChangeNotifierProvider<AudioPlayerService>((ref) {
  return AudioPlayerService();
});

final exportServiceProvider = Provider<ExportService>((ref) {
  return ExportService();
});

final datasetExportProvider = Provider<DatasetExportService>((ref) {
  return DatasetExportService(ref.watch(localStorageProvider));
});

class AppState {
  const AppState({
    this.initialized = false,
    this.profiles = const [],
    this.datasetRecordings = const [],
    this.history = const [],
    this.backendConfig = const BackendConfig(),
    this.lastHealth,
  });

  final bool initialized;
  final List<VoiceProfile> profiles;
  final List<DatasetRecording> datasetRecordings;
  final List<GeneratedAudio> history;
  final BackendConfig backendConfig;
  final BackendHealth? lastHealth;

  int get totalDatasetDurationMs =>
      datasetRecordings.fold<int>(0, (sum, item) => sum + item.durationMs);

  AppState copyWith({
    bool? initialized,
    List<VoiceProfile>? profiles,
    List<DatasetRecording>? datasetRecordings,
    List<GeneratedAudio>? history,
    BackendConfig? backendConfig,
    BackendHealth? lastHealth,
    bool clearHealth = false,
  }) {
    return AppState(
      initialized: initialized ?? this.initialized,
      profiles: profiles ?? this.profiles,
      datasetRecordings: datasetRecordings ?? this.datasetRecordings,
      history: history ?? this.history,
      backendConfig: backendConfig ?? this.backendConfig,
      lastHealth: clearHealth ? null : (lastHealth ?? this.lastHealth),
    );
  }
}

class AppStateNotifier extends StateNotifier<AppState> {
  AppStateNotifier(this._storage, this._api) : super(const AppState());

  final LocalStorageService _storage;
  final ApiClientService _api;
  final _uuid = const Uuid();

  Future<void> initialize() async {
    if (state.initialized) return;
    await _storage.init();
    final profiles = await _storage.loadProfiles();
    final dataset = await _storage.loadDatasetRecordings();
    final history = await _storage.loadHistory();
    final config = await _storage.loadBackendConfig();

    state = state.copyWith(
      initialized: true,
      profiles: profiles,
      datasetRecordings: dataset,
      history: history,
      backendConfig: config,
    );
  }

  Future<void> saveProfile(VoiceProfile profile) async {
    await _storage.saveProfile(profile);
    final updated = await _storage.loadProfiles();
    state = state.copyWith(profiles: updated);
  }

  Future<void> deleteProfile(VoiceProfile profile) async {
    await _storage.deleteProfile(profile);
    final updated = await _storage.loadProfiles();
    state = state.copyWith(profiles: updated);
  }

  Future<void> saveDatasetRecording(DatasetRecording item) async {
    await _storage.saveDatasetRecording(item);
    final updated = await _storage.loadDatasetRecordings();
    state = state.copyWith(datasetRecordings: updated);
  }

  Future<void> deleteDatasetRecording(DatasetRecording item) async {
    await _storage.deleteDatasetRecording(item);
    final updated = await _storage.loadDatasetRecordings();
    state = state.copyWith(datasetRecordings: updated);
  }

  Future<void> saveBackendConfig(BackendConfig config) async {
    await _storage.saveBackendConfig(config);
    state = state.copyWith(backendConfig: config, clearHealth: true);
  }

  Future<BackendHealth> testBackendHealth() async {
    final health = await _api.checkHealth(state.backendConfig);
    state = state.copyWith(lastHealth: health);
    return health;
  }

  Future<GeneratedAudio> synthesizeAndSave({
    required VoiceProfile profile,
    required SpeakingStyle style,
    required String text,
    required String languageMode,
    required String outputFormat,
    required double speed,
    required double exaggeration,
    required double cfgWeight,
    required int pauseMs,
    required bool consentConfirmed,
  }) async {
    final result = await _api.synthesize(
      config: state.backendConfig,
      profile: profile,
      style: style,
      text: text,
      languageMode: languageMode,
      outputFormat: outputFormat,
      speed: speed,
      exaggeration: exaggeration,
      cfgWeight: cfgWeight,
      pauseMs: pauseMs,
      consentConfirmed: consentConfirmed,
    );

    final id = _uuid.v4();
    final path = await _storage.createGeneratedAudioPath(id, outputFormat);
    await File(path).writeAsBytes(result.bytes, flush: true);

    final record = GeneratedAudio(
      id: id,
      profileId: profile.id,
      profileName: profile.name,
      text: text,
      languageMode: languageMode,
      outputFormat: outputFormat,
      style: style.apiValue,
      speed: speed,
      engineId: result.engineId,
      isMock: result.isMock,
      filePath: path,
      createdAt: DateTime.now(),
    );

    await _storage.saveGeneratedAudio(record);
    final history = await _storage.loadHistory();
    state = state.copyWith(history: history);
    return record;
  }

  Future<void> deleteGeneratedAudio(GeneratedAudio item) async {
    await _storage.deleteGeneratedAudio(item);
    final history = await _storage.loadHistory();
    state = state.copyWith(history: history);
  }

  Future<void> wipeAllPrivateData() async {
    await _storage.wipeAllPrivateData();
    state = state.copyWith(
      profiles: const [],
      datasetRecordings: const [],
      history: const [],
      backendConfig: state.backendConfig.copyWith(apiToken: ''),
      clearHealth: true,
    );
  }

  Future<Map<String, dynamic>> uploadTrainingDatasetZip({
    required String zipPath,
    required bool consentConfirmed,
    String? datasetId,
  }) async {
    return _api.uploadTrainingDataset(
      config: state.backendConfig,
      zipPath: zipPath,
      consentConfirmed: consentConfirmed,
      datasetId: datasetId,
    );
  }

  Future<Map<String, dynamic>> deleteRemoteTrainingData() async {
    return _api.deleteRemoteTrainingData(state.backendConfig);
  }
}

final appStateProvider = StateNotifierProvider<AppStateNotifier, AppState>((ref) {
  return AppStateNotifier(
    ref.watch(localStorageProvider),
    ref.watch(apiClientProvider),
  );
});
