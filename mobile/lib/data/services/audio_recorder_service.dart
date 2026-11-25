import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:myvoice_ai/core/errors/app_exception.dart';
import 'package:path/path.dart' as p;
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

class PickedAudioFile {
  const PickedAudioFile({
    required this.sourcePath,
    required this.extension,
  });

  final String sourcePath;
  final String extension;
}

class AudioRecorderService {
  final AudioRecorder _recorder = AudioRecorder();
  DateTime? _recordingStartedAt;

  Future<bool> ensureMicrophonePermission() async {
    final status = await Permission.microphone.request();
    if (status.isGranted) return true;
    return await _recorder.hasPermission();
  }

  Future<void> startRecording(String outputWavPath) async {
    final allowed = await ensureMicrophonePermission();
    if (!allowed) {
      throw const AppException('Microphone permission is required to record your voice.');
    }
    _recordingStartedAt = DateTime.now();
    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.wav,
        sampleRate: 24000,
        numChannels: 1,
      ),
      path: outputWavPath,
    );
  }

  Future<int> stopRecording() async {
    final path = await _recorder.stop();
    final startedAt = _recordingStartedAt;
    _recordingStartedAt = null;
    if (path == null || !await File(path).exists()) {
      throw const AppException('Recording failed or produced no audio file.');
    }
    if (startedAt == null) return 0;
    return DateTime.now().difference(startedAt).inMilliseconds;
  }

  Future<PickedAudioFile?> pickAudioFile() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['wav', 'mp3', 'm4a', 'ogg', 'flac'],
    );
    final picked = result?.files.singleOrNull;
    if (picked?.path == null) return null;

    final ext = p.extension(picked!.path!).replaceFirst('.', '').toLowerCase();
    return PickedAudioFile(
      sourcePath: picked.path!,
      extension: ext.isEmpty ? 'wav' : ext,
    );
  }

  Future<void> dispose() async {
    await _recorder.dispose();
  }
}
