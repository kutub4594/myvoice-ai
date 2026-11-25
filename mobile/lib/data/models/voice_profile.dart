import 'dart:convert';

enum ProfileType {
  zeroShot('zero_shot', 'Instant Voice (Zero-Shot)'),
  trainedModel('trained_model', 'Trained Personal Model');

  const ProfileType(this.apiValue, this.label);
  final String apiValue;
  final String label;

  static ProfileType fromApi(String? value) {
    return ProfileType.values.firstWhere(
      (e) => e.apiValue == value,
      orElse: () => ProfileType.zeroShot,
    );
  }
}

enum SpeakingStyle {
  neutral('neutral', 'Neutral'),
  conversational('conversational', 'Conversational'),
  expressive('expressive', 'Expressive'),
  calm('calm', 'Calm');

  const SpeakingStyle(this.apiValue, this.label);
  final String apiValue;
  final String label;

  static SpeakingStyle fromApi(String? value) {
    return SpeakingStyle.values.firstWhere(
      (e) => e.apiValue == value,
      orElse: () => SpeakingStyle.neutral,
    );
  }
}

class VoiceSampleClip {
  const VoiceSampleClip({
    required this.id,
    required this.filePath,
    required this.style,
    required this.language,
    required this.durationMs,
    this.transcript,
  });

  final String id;
  final String filePath;
  final SpeakingStyle style;
  final String language; // 'bn', 'en', 'auto'
  final int durationMs;
  final String? transcript;

  Map<String, dynamic> toJson() => {
        'id': id,
        'filePath': filePath,
        'style': style.apiValue,
        'language': language,
        'durationMs': durationMs,
        'transcript': transcript,
      };

  factory VoiceSampleClip.fromJson(Map<String, dynamic> json) => VoiceSampleClip(
        id: json['id'] as String,
        filePath: json['filePath'] as String,
        style: SpeakingStyle.fromApi(json['style'] as String?),
        language: (json['language'] as String?) ?? 'auto',
        durationMs: (json['durationMs'] as num?)?.toInt() ?? 0,
        transcript: json['transcript'] as String?,
      );
}

class VoiceProfile {
  const VoiceProfile({
    required this.id,
    required this.name,
    required this.profileType,
    required this.clips,
    required this.createdAt,
    required this.updatedAt,
    this.notes = '',
    this.trainedCheckpointId,
  });

  final String id;
  final String name;
  final ProfileType profileType;
  final List<VoiceSampleClip> clips;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String notes;
  final String? trainedCheckpointId;

  VoiceSampleClip? clipForStyle(SpeakingStyle style) {
    if (clips.isEmpty) return null;
    for (final clip in clips) {
      if (clip.style == style) return clip;
    }
    return clips.first;
  }

  VoiceProfile copyWith({
    String? name,
    ProfileType? profileType,
    List<VoiceSampleClip>? clips,
    DateTime? updatedAt,
    String? notes,
    String? trainedCheckpointId,
  }) {
    return VoiceProfile(
      id: id,
      name: name ?? this.name,
      profileType: profileType ?? this.profileType,
      clips: clips ?? this.clips,
      createdAt: createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      notes: notes ?? this.notes,
      trainedCheckpointId: trainedCheckpointId ?? this.trainedCheckpointId,
    );
  }

  Map<String, dynamic> toDbMap() => {
        'id': id,
        'name': name,
        'profile_type': profileType.apiValue,
        'clips_json': jsonEncode(clips.map((c) => c.toJson()).toList()),
        'created_at': createdAt.toIso8601String(),
        'updated_at': updatedAt.toIso8601String(),
        'notes': notes,
        'trained_checkpoint_id': trainedCheckpointId,
      };

  factory VoiceProfile.fromDbMap(Map<String, dynamic> map) {
    final decoded = jsonDecode((map['clips_json'] as String?) ?? '[]') as List<dynamic>;
    return VoiceProfile(
      id: map['id'] as String,
      name: map['name'] as String,
      profileType: ProfileType.fromApi(map['profile_type'] as String?),
      clips: decoded
          .map((item) => VoiceSampleClip.fromJson(item as Map<String, dynamic>))
          .toList(),
      createdAt: DateTime.parse(map['created_at'] as String),
      updatedAt: DateTime.parse(map['updated_at'] as String),
      notes: (map['notes'] as String?) ?? '',
      trainedCheckpointId: map['trained_checkpoint_id'] as String?,
    );
  }
}
