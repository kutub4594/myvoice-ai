import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:myvoice_ai/core/errors/app_exception.dart';
import 'package:myvoice_ai/data/models/dataset_item.dart';
import 'package:myvoice_ai/data/services/local_storage_service.dart';
import 'package:path/path.dart' as p;
import 'package:share_plus/share_plus.dart';

class DatasetExportResult {
  const DatasetExportResult({required this.zipPath, required this.clipCount});

  final String zipPath;
  final int clipCount;
}

class DatasetExportService {
  DatasetExportService(this._storage);

  final LocalStorageService _storage;

  /// Builds an LJSpeech-style ZIP (wavs/ + metadata.csv) inside app-private storage.
  Future<DatasetExportResult> buildDatasetZipFile(
    List<DatasetRecording> recordings, {
    required bool consentConfirmed,
    bool forImmediateUpload = false,
  }) async {
    if (!consentConfirmed) {
      throw const AppException(
        'Explicit user consent is required before packaging or transferring training recordings.',
      );
    }
    if (recordings.isEmpty) {
      throw const AppException('Record at least one dataset utterance before exporting.');
    }

    final archive = Archive();
    final metadataLines = <String>[];

    for (var i = 0; i < recordings.length; i++) {
      final item = recordings[i];
      final audioFile = File(item.filePath);
      if (!await audioFile.exists()) continue;

      final wavName = 'utt_${(i + 1).toString().padLeft(4, '0')}.wav';
      final bytes = await audioFile.readAsBytes();
      archive.addFile(ArchiveFile(p.posix.join('wavs', wavName), bytes.length, bytes));

      final safeTranscript = item.transcript.replaceAll('|', ' ').replaceAll('\n', ' ').trim();
      metadataLines.add('$wavName|$safeTranscript|${item.language}|${item.styleHint}');
    }

    if (metadataLines.isEmpty) {
      throw const AppException('No valid audio files were found on disk for export.');
    }

    final metadataBytes = utf8.encode(metadataLines.join('\n'));
    archive.addFile(ArchiveFile('metadata.csv', metadataBytes.length, metadataBytes));

    final zipBytes = ZipEncoder().encode(archive);
    if (zipBytes == null) {
      throw const AppException('Failed to encode dataset ZIP archive.');
    }

    final zipPath = forImmediateUpload
        ? await _storage.createTemporaryUploadZipPath()
        : await _storage.createDatasetExportZipPath();
    await File(zipPath).writeAsBytes(zipBytes, flush: true);
    return DatasetExportResult(zipPath: zipPath, clipCount: metadataLines.length);
  }

  /// Packages recorded personal dataset clips and opens the system share sheet after explicit consent.
  Future<String> buildAndShareDatasetZip(
    List<DatasetRecording> recordings, {
    bool consentConfirmed = false,
  }) async {
    final result = await buildDatasetZipFile(
      recordings,
      consentConfirmed: consentConfirmed,
    );

    await SharePlus.instance.share(
      ShareParams(
        files: [XFile(result.zipPath, mimeType: 'application/zip')],
        subject: 'MyVoice AI Personal Voice Dataset (${result.clipCount} clips)',
      ),
    );

    return result.zipPath;
  }
}
