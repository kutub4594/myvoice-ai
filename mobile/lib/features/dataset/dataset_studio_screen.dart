import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:myvoice_ai/core/constants/app_constants.dart';
import 'package:myvoice_ai/core/constants/guided_prompts.dart';
import 'package:myvoice_ai/data/models/dataset_item.dart';
import 'package:myvoice_ai/data/providers/app_providers.dart';
import 'package:uuid/uuid.dart';

class DatasetStudioScreen extends ConsumerStatefulWidget {
  const DatasetStudioScreen({super.key});

  @override
  ConsumerState<DatasetStudioScreen> createState() => _DatasetStudioScreenState();
}

class _DatasetStudioScreenState extends ConsumerState<DatasetStudioScreen> {
  final _uuid = const Uuid();
  int _promptIndex = 0;
  bool _isRecording = false;
  bool _isExporting = false;
  bool _isUploading = false;
  bool _isDeletingRemote = false;
  String? _pendingPath;
  String? _errorText;
  String? _statusText;

  GuidedPrompt get _currentPrompt => GuidedPrompts.all[_promptIndex];

  Future<void> _toggleRecordPrompt() async {
    final recorder = ref.read(audioRecorderProvider);
    final storage = ref.read(localStorageProvider);
    setState(() => _errorText = null);

    try {
      if (!_isRecording) {
        final id = _uuid.v4();
        final path = await storage.createDatasetClipPath(id);
        await recorder.startRecording(path);
        setState(() {
          _isRecording = true;
          _pendingPath = path;
        });
      } else {
        final durationMs = await recorder.stopRecording();
        final path = _pendingPath;
        setState(() {
          _isRecording = false;
          _pendingPath = null;
        });
        if (path != null) {
          final recording = DatasetRecording(
            id: _uuid.v4(),
            promptId: _currentPrompt.id,
            language: _currentPrompt.language,
            styleHint: _currentPrompt.styleHint,
            transcript: _currentPrompt.text,
            filePath: path,
            durationMs: durationMs,
            createdAt: DateTime.now(),
          );
          await ref.read(appStateProvider.notifier).saveDatasetRecording(recording);
        }
      }
    } catch (e) {
      setState(() {
        _isRecording = false;
        _errorText = e.toString();
      });
    }
  }

  Future<bool> _askExplicitTrainingConsent({
    required String title,
    required String destinationLabel,
    required int clipCount,
    required String actionLabel,
  }) async {
    var acknowledged = false;
    final approved = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: Text(title),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'You are about to transfer $clipCount personal voice recording(s) and '
                'transcripts from app-private storage to:\n$destinationLabel\n\n'
                'Training uploads NEVER occur silently and consent is asked every time.',
              ),
              const SizedBox(height: 12),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: acknowledged,
                onChanged: (v) => setDialogState(() => acknowledged = v ?? false),
                title: const Text(
                  'I confirm this is my own voice (or I have explicit permission) and I consent to this upload.',
                ),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(
              onPressed: acknowledged ? () => Navigator.pop(ctx, true) : null,
              child: Text(actionLabel),
            ),
          ],
        ),
      ),
    );
    return approved == true && acknowledged;
  }

  Future<void> _exportDatasetZip(List<DatasetRecording> recordings) async {
    final consented = await _askExplicitTrainingConsent(
      title: 'Confirm Local Dataset Export',
      destinationLabel: 'Android system share sheet (user-selected destination)',
      clipCount: recordings.length,
      actionLabel: 'Consent & Export ZIP',
    );
    if (!consented) return;

    setState(() {
      _isExporting = true;
      _errorText = null;
      _statusText = null;
    });
    try {
      await ref
          .read(datasetExportProvider)
          .buildAndShareDatasetZip(recordings, consentConfirmed: true);
    } catch (e) {
      setState(() => _errorText = e.toString());
    } finally {
      if (mounted) setState(() => _isExporting = false);
    }
  }

  Future<void> _uploadDatasetToBackend(List<DatasetRecording> recordings) async {
    final backendUrl = ref.read(appStateProvider).backendConfig.baseUrl;
    final consented = await _askExplicitTrainingConsent(
      title: 'Explicit Training Upload Consent',
      destinationLabel: '$backendUrl (private external GPU storage, outside Git)',
      clipCount: recordings.length,
      actionLabel: 'I Consent & Upload',
    );
    if (!consented) return;

    setState(() {
      _isUploading = true;
      _errorText = null;
      _statusText = null;
    });
    String? tempZipPath;
    try {
      final zipResult = await ref.read(datasetExportProvider).buildDatasetZipFile(
            recordings,
            consentConfirmed: true,
            forImmediateUpload: true,
          );
      tempZipPath = zipResult.zipPath;

      final resp = await ref.read(appStateProvider.notifier).uploadTrainingDatasetZip(
            zipPath: tempZipPath,
            consentConfirmed: true,
          );
      setState(() {
        _statusText =
            'Uploaded ${resp['file_count'] ?? zipResult.clipCount} file(s) to private remote storage '
            '(dataset_id: ${resp['dataset_id'] ?? 'created'}).';
      });
    } catch (e) {
      setState(() => _errorText = e.toString());
    } finally {
      if (tempZipPath != null) {
        final f = File(tempZipPath);
        if (await f.exists()) await f.delete();
      }
      if (mounted) setState(() => _isUploading = false);
    }
  }

  Future<void> _deleteRemoteTrainingData() async {
    final backendUrl = ref.read(appStateProvider).backendConfig.baseUrl;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Remote Training Data?'),
        content: Text(
          'This permanently deletes all uploaded datasets, speaker embeddings, generated audio, '
          'and checkpoints stored in private backend storage at:\n$backendUrl',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete Remote Data'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() {
      _isDeletingRemote = true;
      _errorText = null;
      _statusText = null;
    });
    try {
      final resp = await ref.read(appStateProvider.notifier).deleteRemoteTrainingData();
      setState(() {
        _statusText =
            'Remote private training storage cleared (${resp['deleted_items'] ?? 0} item(s) removed).';
      });
    } catch (e) {
      setState(() => _errorText = e.toString());
    } finally {
      if (mounted) setState(() => _isDeletingRemote = false);
    }
  }

  Future<void> _editTranscript(DatasetRecording item) async {
    final ctrl = TextEditingController(text: item.transcript);
    final updated = await showDialog<String?>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit Utterance Transcript'),
        content: TextField(
          controller: ctrl,
          maxLines: 3,
          decoration: const InputDecoration(labelText: 'Exact spoken words'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    ctrl.dispose();
    if (updated != null && updated.isNotEmpty) {
      await ref
          .read(appStateProvider.notifier)
          .saveDatasetRecording(item.copyWith(transcript: updated));
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(appStateProvider);
    final player = ref.watch(audioPlayerProvider);
    final recordings = state.datasetRecordings;
    final totalMinutes = state.totalDatasetDurationMs / 60000.0;
    final progress = (totalMinutes / AppConstants.targetDatasetMinutes).clamp(0.0, 1.0);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Tier 2: Dataset Studio'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: FilledButton.tonalIcon(
              onPressed: _isExporting || recordings.isEmpty
                  ? null
                  : () => _exportDatasetZip(recordings),
              icon: _isExporting
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.archive_outlined),
              label: const Text('Export ZIP'),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Personal Fine-Tuning Dataset Progress',
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 6),
                  Text(
                    '${recordings.length} clip(s) • ${totalMinutes.toStringAsFixed(1)} / '
                    '${AppConstants.targetDatasetMinutes}.0 min minimum target for Colab fine-tuning',
                  ),
                  const SizedBox(height: 10),
                  LinearProgressIndicator(value: progress),
                  const SizedBox(height: 8),
                  Text(
                    'All clips stay stored privately inside Android app-private storage. '
                    'Any ZIP export or GPU backend upload requires your explicit consent every time.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      FilledButton.tonalIcon(
                        onPressed: _isUploading || _isExporting || recordings.isEmpty
                            ? null
                            : () => _uploadDatasetToBackend(recordings),
                        icon: _isUploading
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.cloud_upload_outlined),
                        label: const Text('Upload to GPU Backend'),
                      ),
                      OutlinedButton.icon(
                        onPressed: _isDeletingRemote ? null : _deleteRemoteTrainingData,
                        icon: _isDeletingRemote
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.cloud_off_outlined),
                        label: const Text('Delete Remote Data'),
                      ),
                    ],
                  ),
                  if (_statusText != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      _statusText!,
                      style: TextStyle(color: Theme.of(context).colorScheme.primary),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Chip(
                        label: Text(
                          '${_currentPrompt.language == 'bn' ? 'Bengali' : 'English'} • ${_currentPrompt.styleHint}',
                        ),
                      ),
                      Text('Prompt ${_promptIndex + 1} / ${GuidedPrompts.all.length}'),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    _currentPrompt.text,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      IconButton.outlined(
                        onPressed: _isRecording
                            ? null
                            : () => setState(() {
                                  _promptIndex = (_promptIndex - 1 + GuidedPrompts.all.length) %
                                      GuidedPrompts.all.length;
                                }),
                        icon: const Icon(Icons.chevron_left),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: _toggleRecordPrompt,
                          icon: Icon(_isRecording ? Icons.stop : Icons.mic),
                          label: Text(_isRecording ? 'Stop & Save Clip' : 'Record Sentence'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.outlined(
                        onPressed: _isRecording
                            ? null
                            : () => setState(() {
                                  _promptIndex = (_promptIndex + 1) % GuidedPrompts.all.length;
                                }),
                        icon: const Icon(Icons.chevron_right),
                      ),
                    ],
                  ),
                  if (_errorText != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      _errorText!,
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('Recorded Dataset Clips (${recordings.length})',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          if (recordings.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text('No dataset recordings yet. Use the guided prompt card above.'),
              ),
            )
          else
            for (final item in recordings)
              Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: IconButton(
                    icon: Icon(
                      player.activePath == item.filePath && player.isPlaying
                          ? Icons.pause_circle
                          : Icons.play_circle,
                    ),
                    onPressed: () => player.togglePlayFile(item.filePath),
                  ),
                  title: Text(item.transcript, maxLines: 2, overflow: TextOverflow.ellipsis),
                  subtitle: Text(
                    '${item.language.toUpperCase()} • ${item.styleHint} • '
                    '${(item.durationMs / 1000).toStringAsFixed(1)}s',
                  ),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: const Icon(Icons.edit_outlined),
                        onPressed: () => _editTranscript(item),
                      ),
                      IconButton(
                        icon: const Icon(Icons.delete_outline),
                        onPressed: () async {
                          await player.stopIfActive(item.filePath);
                          await ref.read(appStateProvider.notifier).deleteDatasetRecording(item);
                        },
                      ),
                    ],
                  ),
                ),
              ),
        ],
      ),
    );
  }
}
