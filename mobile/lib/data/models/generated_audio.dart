class GeneratedAudio {
  const GeneratedAudio({
    required this.id,
    required this.profileId,
    required this.profileName,
    required this.text,
    required this.languageMode,
    required this.outputFormat,
    required this.style,
    required this.speed,
    required this.engineId,
    required this.isMock,
    required this.filePath,
    required this.createdAt,
  });

  final String id;
  final String profileId;
  final String profileName;
  final String text;
  final String languageMode;
  final String outputFormat; // 'wav' or 'mp3'
  final String style;
  final double speed;
  final String engineId;
  final bool isMock;
  final String filePath;
  final DateTime createdAt;

  Map<String, dynamic> toDbMap() => {
        'id': id,
        'profile_id': profileId,
        'profile_name': profileName,
        'text': text,
        'language_mode': languageMode,
        'output_format': outputFormat,
        'style': style,
        'speed': speed,
        'engine_id': engineId,
        'is_mock': isMock ? 1 : 0,
        'file_path': filePath,
        'created_at': createdAt.toIso8601String(),
      };

  factory GeneratedAudio.fromDbMap(Map<String, dynamic> map) => GeneratedAudio(
        id: map['id'] as String,
        profileId: map['profile_id'] as String,
        profileName: map['profile_name'] as String,
        text: map['text'] as String,
        languageMode: map['language_mode'] as String,
        outputFormat: map['output_format'] as String,
        style: (map['style'] as String?) ?? 'neutral',
        speed: (map['speed'] as num?)?.toDouble() ?? 1.0,
        engineId: (map['engine_id'] as String?) ?? 'unknown',
        isMock: ((map['is_mock'] as num?)?.toInt() ?? 0) == 1,
        filePath: map['file_path'] as String,
        createdAt: DateTime.parse(map['created_at'] as String),
      );
}
