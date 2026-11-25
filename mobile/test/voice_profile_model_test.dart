import 'package:flutter_test/flutter_test.dart';
import 'package:myvoice_ai/data/models/voice_profile.dart';

void main() {
  test('VoiceProfile round-trips through DB map and resolves style clips', () {
    final now = DateTime(2026, 11, 26, 1, 0);
    final profile = VoiceProfile(
      id: 'p1',
      name: 'Personal Voice',
      profileType: ProfileType.zeroShot,
      clips: const [
        VoiceSampleClip(
          id: 'c1',
          filePath: '/vault/c1.wav',
          style: SpeakingStyle.neutral,
          language: 'bn',
          durationMs: 7500,
          transcript: 'নমস্কার',
        ),
        VoiceSampleClip(
          id: 'c2',
          filePath: '/vault/c2.wav',
          style: SpeakingStyle.expressive,
          language: 'en',
          durationMs: 6200,
        ),
      ],
      createdAt: now,
      updatedAt: now,
    );

    final restored = VoiceProfile.fromDbMap(profile.toDbMap());
    expect(restored.name, 'Personal Voice');
    expect(restored.profileType, ProfileType.zeroShot);
    expect(restored.clips.length, 2);
    expect(restored.clipForStyle(SpeakingStyle.expressive)?.id, 'c2');
    expect(restored.clipForStyle(SpeakingStyle.calm)?.id, 'c1');
  });
}
