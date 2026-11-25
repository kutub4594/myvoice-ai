class EngineMetadata {
  const EngineMetadata({
    required this.id,
    required this.name,
    required this.status,
    required this.isMock,
    required this.supportsBengali,
    required this.supportsEnglish,
    required this.supportsStyleControls,
    required this.supportsTrainedCheckpoints,
    required this.requiresGpu,
    required this.models,
    required this.licenses,
    required this.notes,
  });

  final String id;
  final String name;
  final String status;
  final bool isMock;
  final bool supportsBengali;
  final bool supportsEnglish;
  final bool supportsStyleControls;
  final bool supportsTrainedCheckpoints;
  final bool requiresGpu;
  final List<String> models;
  final List<String> licenses;
  final String notes;

  factory EngineMetadata.fromJson(Map<String, dynamic> json) => EngineMetadata(
        id: (json['id'] as String?) ?? 'unknown',
        name: (json['name'] as String?) ?? 'Unknown Engine',
        status: (json['status'] as String?) ?? 'unavailable',
        isMock: (json['is_mock'] as bool?) ?? false,
        supportsBengali: (json['supports_bengali'] as bool?) ?? false,
        supportsEnglish: (json['supports_english'] as bool?) ?? false,
        supportsStyleControls: (json['supports_style_controls'] as bool?) ?? false,
        supportsTrainedCheckpoints: (json['supports_trained_checkpoints'] as bool?) ?? false,
        requiresGpu: (json['requires_gpu'] as bool?) ?? false,
        models: ((json['models'] as List<dynamic>?) ?? const []).cast<String>(),
        licenses: ((json['licenses'] as List<dynamic>?) ?? const []).cast<String>(),
        notes: (json['notes'] as String?) ?? '',
      );
}

class BackendHealth {
  const BackendHealth({
    required this.status,
    required this.appName,
    required this.version,
    required this.activeEngine,
    required this.ffmpegAvailable,
    required this.privacyMode,
  });

  final String status;
  final String appName;
  final String version;
  final EngineMetadata activeEngine;
  final bool ffmpegAvailable;
  final String privacyMode;

  factory BackendHealth.fromJson(Map<String, dynamic> json) => BackendHealth(
        status: (json['status'] as String?) ?? 'degraded',
        appName: (json['app_name'] as String?) ?? 'MyVoice AI Backend',
        version: (json['version'] as String?) ?? '',
        activeEngine: EngineMetadata.fromJson(
          (json['active_engine'] as Map<String, dynamic>?) ?? const {},
        ),
        ffmpegAvailable: (json['ffmpeg_available'] as bool?) ?? false,
        privacyMode: (json['privacy_mode'] as String?) ?? 'ephemeral_stateless',
      );
}
