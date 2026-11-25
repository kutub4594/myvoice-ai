class DatasetRecording {
  const DatasetRecording({
    required this.id,
    required this.promptId,
    required this.language,
    required this.styleHint,
    required this.transcript,
    required this.filePath,
    required this.durationMs,
    required this.createdAt,
  });

  final String id;
  final String promptId;
  final String language; // 'bn' or 'en'
  final String styleHint;
  final String transcript;
  final String filePath;
  final int durationMs;
  final DateTime createdAt;

  DatasetRecording copyWith({
    String? transcript,
    String? filePath,
    int? durationMs,
  }) {
    return DatasetRecording(
      id: id,
      promptId: promptId,
      language: language,
      styleHint: styleHint,
      transcript: transcript ?? this.transcript,
      filePath: filePath ?? this.filePath,
      durationMs: durationMs ?? this.durationMs,
      createdAt: createdAt,
    );
  }

  Map<String, dynamic> toDbMap() => {
        'id': id,
        'prompt_id': promptId,
        'language': language,
        'style_hint': styleHint,
        'transcript': transcript,
        'file_path': filePath,
        'duration_ms': durationMs,
        'created_at': createdAt.toIso8601String(),
      };

  factory DatasetRecording.fromDbMap(Map<String, dynamic> map) => DatasetRecording(
        id: map['id'] as String,
        promptId: map['prompt_id'] as String,
        language: map['language'] as String,
        styleHint: (map['style_hint'] as String?) ?? 'Neutral',
        transcript: map['transcript'] as String,
        filePath: map['file_path'] as String,
        durationMs: (map['duration_ms'] as num?)?.toInt() ?? 0,
        createdAt: DateTime.parse(map['created_at'] as String),
      );
}
