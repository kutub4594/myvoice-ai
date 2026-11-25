import 'package:flutter_test/flutter_test.dart';
import 'package:myvoice_ai/core/utils/script_detector.dart';

void main() {
  group('ScriptDetector', () {
    test('detects Bengali, English, mixed, and empty strings', () {
      expect(ScriptDetector.detect(''), DetectedScript.empty);
      expect(ScriptDetector.detect('আমি বাংলায় কথা বলি'), DetectedScript.bengali);
      expect(ScriptDetector.detect('Hello MyVoice AI'), DetectedScript.english);
      expect(ScriptDetector.detect('আজকে আমি office যাচ্ছি'), DetectedScript.mixed);
    });

    test('segments mixed Bengali and English text sequentially', () {
      final segments = ScriptDetector.previewSegments('আমি Flutter এবং Python ব্যবহার করি।');
      expect(segments.length, 5);
      expect(segments[0].languageCode, 'bn');
      expect(segments[0].text, 'আমি');
      expect(segments[1].languageCode, 'en');
      expect(segments[1].text, 'Flutter');
      expect(segments[2].languageCode, 'bn');
      expect(segments[2].text, 'এবং');
      expect(segments[3].languageCode, 'en');
      expect(segments[3].text, 'Python');
      expect(segments[4].languageCode, 'bn');
      expect(segments[4].text, 'ব্যবহার করি।');
    });

    test('groups adjacent same-script tokens and attaches leading numbers cleanly', () {
      final mixed = ScriptDetector.previewSegments(
        'আজকে আমি office থেকে বাড়ি ফিরব। See you soon!',
      );
      expect(mixed.map((s) => s.languageCode).toList(), ['bn', 'en', 'bn', 'en']);
      expect(mixed[0].text, 'আজকে আমি');
      expect(mixed[2].text, 'থেকে বাড়ি ফিরব।');
      expect(mixed[3].text, 'See you soon!');

      final leadingNum = ScriptDetector.previewSegments('2026 MyVoice বাংলা');
      expect(leadingNum.length, 2);
      expect(leadingNum[0].languageCode, 'en');
      expect(leadingNum[0].text, '2026 MyVoice');
      expect(leadingNum[1].languageCode, 'bn');
      expect(leadingNum[1].text, 'বাংলা');

      expect(ScriptDetector.previewSegments('   \n  '), isEmpty);
    });
  });
}
