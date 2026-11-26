import 'dart:io';

import 'package:myvoice_ai/core/constants/app_constants.dart';
import 'package:myvoice_ai/data/models/backend_config.dart';
import 'package:myvoice_ai/data/models/dataset_item.dart';
import 'package:myvoice_ai/data/models/generated_audio.dart';
import 'package:myvoice_ai/data/models/voice_profile.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

class LocalStorageService {
  Database? _db;
  Directory? _rootDir;

  Future<void> init() async {
    if (_db != null) return;
    final appDir = await getApplicationDocumentsDirectory();
    _rootDir = Directory(p.join(appDir.path, 'myvoice_vault'));
    await _rootDir!.create(recursive: true);

    await Directory(p.join(_rootDir!.path, 'profiles')).create(recursive: true);
    await Directory(p.join(_rootDir!.path, 'dataset')).create(recursive: true);
    await Directory(p.join(_rootDir!.path, 'generated')).create(recursive: true);
    await Directory(p.join(_rootDir!.path, 'exports')).create(recursive: true);
    await Directory(p.join(_rootDir!.path, 'tmp_upload')).create(recursive: true);
    await cleanupStaleExportZips(maxAge: const Duration(hours: 1));

    final dbPath = p.join(_rootDir!.path, 'myvoice.db');
    _db = await openDatabase(
      dbPath,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE voice_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            profile_type TEXT NOT NULL,
            clips_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            notes TEXT,
            trained_checkpoint_id TEXT
          )
        ''');
        await db.execute('''
          CREATE TABLE dataset_recordings (
            id TEXT PRIMARY KEY,
            prompt_id TEXT NOT NULL,
            language TEXT NOT NULL,
            style_hint TEXT NOT NULL,
            transcript TEXT NOT NULL,
            file_path TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at TEXT NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE generated_history (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            profile_name TEXT NOT NULL,
            text TEXT NOT NULL,
            language_mode TEXT NOT NULL,
            output_format TEXT NOT NULL,
            style TEXT NOT NULL,
            speed REAL NOT NULL,
            engine_id TEXT NOT NULL,
            is_mock INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            created_at TEXT NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
          )
        ''');
      },
    );
  }

  Database get _database {
    final db = _db;
    if (db == null) {
      throw StateError('LocalStorageService.init() must be called before use.');
    }
    return db;
  }

  Future<String> createProfileClipPath(String clipId, {String ext = 'wav'}) async {
    await init();
    return p.join(_rootDir!.path, 'profiles', '$clipId.$ext');
  }

  Future<String> createDatasetClipPath(String itemId) async {
    await init();
    return p.join(_rootDir!.path, 'dataset', '$itemId.wav');
  }

  Future<String> createGeneratedAudioPath(String itemId, String ext) async {
    await init();
    return p.join(_rootDir!.path, 'generated', '$itemId.$ext');
  }

  Future<String> createDatasetExportZipPath() async {
    await init();
    // Retain recent share exports briefly so Android share targets can read asynchronously,
    // while removing older stale archives cleanly.
    await cleanupStaleExportZips(maxAge: const Duration(hours: 1));
    final ts = DateTime.now().millisecondsSinceEpoch;
    return p.join(_rootDir!.path, 'exports', 'myvoice_dataset_$ts.zip');
  }

  /// Creates an isolated temporary ZIP path strictly for synchronous HTTPS backend upload.
  Future<String> createTemporaryUploadZipPath() async {
    await init();
    await _purgeDirectoryFiles(Directory(p.join(_rootDir!.path, 'tmp_upload')));
    final ts = DateTime.now().millisecondsSinceEpoch;
    return p.join(_rootDir!.path, 'tmp_upload', 'myvoice_upload_$ts.zip');
  }

  Future<void> cleanupStaleExportZips({Duration maxAge = const Duration(hours: 1)}) async {
    if (_rootDir == null) return;
    final exportsDir = Directory(p.join(_rootDir!.path, 'exports'));
    if (!await exportsDir.exists()) return;
    final cutoff = DateTime.now().subtract(maxAge);
    await for (final entity in exportsDir.list()) {
      if (entity is File) {
        if (maxAge <= Duration.zero) {
          await entity.delete();
        } else {
          final stat = await entity.stat();
          if (stat.modified.isBefore(cutoff)) {
            await entity.delete();
          }
        }
      }
    }
  }

  Future<void> _purgeDirectoryFiles(Directory dir) async {
    if (!await dir.exists()) return;
    await for (final entity in dir.list()) {
      if (entity is File) {
        await entity.delete();
      }
    }
  }

  Future<String> copyFileIntoVault(String sourcePath, String destinationPath) async {
    final src = File(sourcePath);
    await src.copy(destinationPath);
    return destinationPath;
  }

  Future<List<VoiceProfile>> loadProfiles() async {
    await init();
    final rows = await _database.query('voice_profiles', orderBy: 'updated_at DESC');
    return rows.map(VoiceProfile.fromDbMap).toList();
  }

  Future<void> saveProfile(VoiceProfile profile) async {
    await init();
    await _database.insert(
      'voice_profiles',
      profile.toDbMap(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> deleteProfile(VoiceProfile profile) async {
    await init();
    await _database.delete('voice_profiles', where: 'id = ?', whereArgs: [profile.id]);
    for (final clip in profile.clips) {
      await _deleteFileIfExists(clip.filePath);
    }
  }

  Future<List<DatasetRecording>> loadDatasetRecordings() async {
    await init();
    final rows = await _database.query('dataset_recordings', orderBy: 'created_at DESC');
    return rows.map(DatasetRecording.fromDbMap).toList();
  }

  Future<void> saveDatasetRecording(DatasetRecording item) async {
    await init();
    await _database.insert(
      'dataset_recordings',
      item.toDbMap(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> deleteDatasetRecording(DatasetRecording item) async {
    await init();
    await _database.delete('dataset_recordings', where: 'id = ?', whereArgs: [item.id]);
    await _deleteFileIfExists(item.filePath);
  }

  Future<List<GeneratedAudio>> loadHistory() async {
    await init();
    final rows = await _database.query('generated_history', orderBy: 'created_at DESC');
    return rows.map(GeneratedAudio.fromDbMap).toList();
  }

  Future<void> saveGeneratedAudio(GeneratedAudio item) async {
    await init();
    await _database.insert(
      'generated_history',
      item.toDbMap(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> deleteGeneratedAudio(GeneratedAudio item) async {
    await init();
    await _database.delete('generated_history', where: 'id = ?', whereArgs: [item.id]);
    await _deleteFileIfExists(item.filePath);
  }

  Future<BackendConfig> loadBackendConfig() async {
    await init();
    // Purge any legacy persisted consent flag so every cloud upload requires fresh consent.
    await _database.delete('app_settings', where: 'key = ?', whereArgs: ['upload_consent']);
    final rows = await _database.query('app_settings');
    final map = <String, String>{
      for (final row in rows) row['key'] as String: row['value'] as String,
    };
    return BackendConfig(
      baseUrl: map['backend_url'] ?? AppConstants.defaultBackendUrl,
      apiToken: map['api_token'] ?? '',
      allowLocalHttpDev: map['allow_local_http_dev'] == 'true',
      requestTimeoutSeconds: int.tryParse(map['timeout_seconds'] ?? '') ?? 90,
    );
  }

  Future<void> saveBackendConfig(BackendConfig config) async {
    await init();
    await _setSetting('backend_url', config.baseUrl.trim());
    await _setSetting('api_token', config.apiToken.trim());
    await _setSetting('allow_local_http_dev', config.allowLocalHttpDev.toString());
    await _setSetting('timeout_seconds', config.requestTimeoutSeconds.toString());
  }

  Future<void> wipeAllPrivateData() async {
    await init();
    await _database.delete('voice_profiles');
    await _database.delete('dataset_recordings');
    await _database.delete('generated_history');
    await _database.delete(
      'app_settings',
      where: 'key IN (?, ?)',
      whereArgs: ['api_token', 'upload_consent'],
    );

    for (final folder in const ['profiles', 'dataset', 'generated', 'exports', 'tmp_upload']) {
      final dir = Directory(p.join(_rootDir!.path, folder));
      if (await dir.exists()) {
        await dir.delete(recursive: true);
      }
      await dir.create(recursive: true);
    }
  }

  Future<void> _setSetting(String key, String value) async {
    await _database.insert(
      'app_settings',
      {'key': key, 'value': value},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> _deleteFileIfExists(String path) async {
    final file = File(path);
    if (await file.exists()) {
      await file.delete();
    }
  }
}
