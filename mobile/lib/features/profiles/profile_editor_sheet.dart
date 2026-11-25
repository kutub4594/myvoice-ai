import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:myvoice_ai/data/models/voice_profile.dart';
import 'package:myvoice_ai/data/providers/app_providers.dart';
import 'package:uuid/uuid.dart';

class ProfileEditorSheet extends ConsumerStatefulWidget {
  const ProfileEditorSheet({super.key, this.existingProfile});

  final VoiceProfile? existingProfile;

  @override
  ConsumerState<ProfileEditorSheet> createState() => _ProfileEditorSheetState();
}

class _ProfileEditorSheetState extends ConsumerState<ProfileEditorSheet> {
  final _formKey = GlobalKey<FormState>();
  final _uuid = const Uuid();
  late final TextEditingController _nameController;
  late final TextEditingController _notesController;
  late final TextEditingController _checkpointController;

  late ProfileType _profileType;
  late List<VoiceSampleClip> _clips;
  final List<String> _newlyCreatedPaths = [];
  final List<String> _removedSavedPaths = [];
  bool _saved = false;
  SpeakingStyle _pendingStyle = SpeakingStyle.neutral;
  String _pendingLang = 'auto';
  bool _isRecording = false;
  String? _pendingRecordPath;
  String? _errorText;

  @override
  void initState() {
    super.initState();
    final p = widget.existingProfile;
    _nameController = TextEditingController(text: p?.name ?? '');
    _notesController = TextEditingController(text: p?.notes ?? '');
    _checkpointController = TextEditingController(text: p?.trainedCheckpointId ?? '');
    _profileType = p?.profileType ?? ProfileType.zeroShot;
    _clips = List<VoiceSampleClip>.from(p?.clips ?? const []);
  }

  @override
  void dispose() {
    if (!_saved) {
      for (final path in _newlyCreatedPaths) {
        final file = File(path);
        if (file.existsSync()) {
          file.deleteSync();
        }
      }
      if (_pendingRecordPath != null) {
        final file = File(_pendingRecordPath!);
        if (file.existsSync()) {
          file.deleteSync();
        }
      }
    }
    _nameController.dispose();
    _notesController.dispose();
    _checkpointController.dispose();
    super.dispose();
  }

  Future<void> _toggleRecording() async {
    final recorder = ref.read(audioRecorderProvider);
    final storage = ref.read(localStorageProvider);
    setState(() => _errorText = null);

    try {
      if (!_isRecording) {
        final clipId = _uuid.v4();
        final path = await storage.createProfileClipPath(clipId, ext: 'wav');
        await recorder.startRecording(path);
        setState(() {
          _isRecording = true;
          _pendingRecordPath = path;
        });
      } else {
        final durationMs = await recorder.stopRecording();
        final path = _pendingRecordPath;
        setState(() {
          _isRecording = false;
          _pendingRecordPath = null;
        });
        if (path != null) {
          _newlyCreatedPaths.add(path);
          await _promptTranscriptAndAddClip(
            filePath: path,
            durationMs: durationMs,
          );
        }
      }
    } catch (e) {
      setState(() {
        _isRecording = false;
        _errorText = e.toString();
      });
    }
  }

  Future<void> _pickAudioFile() async {
    final recorder = ref.read(audioRecorderProvider);
    final storage = ref.read(localStorageProvider);
    setState(() => _errorText = null);

    try {
      final picked = await recorder.pickAudioFile();
      if (picked == null) return;
      final clipId = _uuid.v4();
      final dest = await storage.createProfileClipPath(clipId, ext: picked.extension);
      await storage.copyFileIntoVault(picked.sourcePath, dest);
      _newlyCreatedPaths.add(dest);
      await _promptTranscriptAndAddClip(filePath: dest, durationMs: 0);
    } catch (e) {
      setState(() => _errorText = e.toString());
    }
  }

  Future<void> _promptTranscriptAndAddClip({
    required String filePath,
    required int durationMs,
  }) async {
    final transcriptCtrl = TextEditingController();
    final transcript = await showDialog<String?>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Optional Reference Transcript'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Adding the exact spoken words improves IndicF5 / F5-TTS voice cloning accuracy. '
              'You can also leave it blank to use backend auto-transcription later.',
            ),
            const SizedBox(height: 12),
            TextField(
              controller: transcriptCtrl,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: 'Spoken transcript (Bengali or English)',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, ''),
            child: const Text('Skip'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, transcriptCtrl.text.trim()),
            child: const Text('Save Clip'),
          ),
        ],
      ),
    );
    transcriptCtrl.dispose();

    final clip = VoiceSampleClip(
      id: _uuid.v4(),
      filePath: filePath,
      style: _pendingStyle,
      language: _pendingLang,
      durationMs: durationMs,
      transcript: (transcript ?? '').isEmpty ? null : transcript,
    );
    setState(() => _clips.add(clip));
  }

  Future<void> _saveProfile() async {
    if (_isRecording) {
      setState(() => _errorText = 'Stop recording before saving the profile.');
      return;
    }
    if (!(_formKey.currentState?.validate() ?? false)) return;
    if (_profileType == ProfileType.zeroShot && _clips.isEmpty) {
      setState(() => _errorText = 'Record or upload at least one reference voice clip.');
      return;
    }

    final now = DateTime.now();
    final existing = widget.existingProfile;
    final profile = VoiceProfile(
      id: existing?.id ?? _uuid.v4(),
      name: _nameController.text.trim(),
      profileType: _profileType,
      clips: _clips,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
      notes: _notesController.text.trim(),
      trainedCheckpointId: _profileType == ProfileType.trainedModel
          ? _checkpointController.text.trim()
          : null,
    );

    await ref.read(appStateProvider.notifier).saveProfile(profile);
    for (final path in _removedSavedPaths) {
      await ref.read(audioPlayerProvider).stopIfActive(path);
      final file = File(path);
      if (await file.exists()) {
        await file.delete();
      }
    }
    _saved = true;
    if (mounted) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    final player = ref.watch(audioPlayerProvider);
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;

    return Padding(
      padding: EdgeInsets.fromLTRB(16, 16, 16, 16 + bottomInset),
      child: SingleChildScrollView(
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                widget.existingProfile == null ? 'New Voice Profile' : 'Edit Voice Profile',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _nameController,
                decoration: const InputDecoration(
                  labelText: 'Profile Name',
                  hintText: 'e.g. My Personal Voice',
                ),
                validator: (val) =>
                    (val == null || val.trim().isEmpty) ? 'Profile name is required' : null,
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<ProfileType>(
                value: _profileType,
                decoration: const InputDecoration(labelText: 'Voice Cloning Tier'),
                items: ProfileType.values
                    .map((t) => DropdownMenuItem(value: t, child: Text(t.label)))
                    .toList(),
                onChanged: (val) {
                  if (val != null) setState(() => _profileType = val);
                },
              ),
              const SizedBox(height: 8),
              Text(
                _profileType == ProfileType.zeroShot
                    ? 'Tier 1 (Zero-Shot): Uses short reference recordings without training weights.'
                    : 'Tier 2 (Trained): Uses a fine-tuned personal checkpoint created in Google Colab.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              if (_profileType == ProfileType.trainedModel) ...[
                const SizedBox(height: 12),
                TextFormField(
                  controller: _checkpointController,
                  decoration: const InputDecoration(
                    labelText: 'Trained Checkpoint ID',
                    hintText: 'e.g. my_f5_checkpoint_v1',
                  ),
                  validator: (val) {
                    if (_profileType == ProfileType.trainedModel &&
                        (val == null || val.trim().isEmpty)) {
                      return 'Checkpoint ID is required for trained profiles';
                    }
                    return null;
                  },
                ),
              ],
              const SizedBox(height: 12),
              TextFormField(
                controller: _notesController,
                decoration: const InputDecoration(
                  labelText: 'Notes (optional)',
                  hintText: 'Mic used, recording room, language focus',
                ),
              ),
              const Divider(height: 24),
              Text('Reference Voice Clips (${_clips.length})',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  DropdownButton<SpeakingStyle>(
                    value: _pendingStyle,
                    items: SpeakingStyle.values
                        .map((s) => DropdownMenuItem(value: s, child: Text(s.label)))
                        .toList(),
                    onChanged: (v) {
                      if (v != null) setState(() => _pendingStyle = v);
                    },
                  ),
                  DropdownButton<String>(
                    value: _pendingLang,
                    items: const [
                      DropdownMenuItem(value: 'auto', child: Text('Auto Lang')),
                      DropdownMenuItem(value: 'bn', child: Text('Bengali')),
                      DropdownMenuItem(value: 'en', child: Text('English')),
                    ],
                    onChanged: (v) {
                      if (v != null) setState(() => _pendingLang = v);
                    },
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: _toggleRecording,
                      icon: Icon(_isRecording ? Icons.stop : Icons.mic),
                      label: Text(_isRecording ? 'Stop Recording' : 'Record Sample'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _isRecording ? null : _pickAudioFile,
                      icon: const Icon(Icons.upload_file),
                      label: const Text('Upload Audio'),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              for (final clip in _clips)
                Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ListTile(
                    leading: IconButton(
                      icon: Icon(
                        player.activePath == clip.filePath && player.isPlaying
                            ? Icons.pause_circle
                            : Icons.play_circle,
                      ),
                      onPressed: () => player.togglePlayFile(clip.filePath),
                    ),
                    title: Text('${clip.style.label} • ${clip.language.toUpperCase()}'),
                    subtitle: Text(
                      clip.transcript ??
                          (clip.durationMs > 0
                              ? '${(clip.durationMs / 1000).toStringAsFixed(1)}s recorded'
                              : 'Uploaded sample'),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: IconButton(
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () async {
                        await player.stopIfActive(clip.filePath);
                        if (_newlyCreatedPaths.remove(clip.filePath)) {
                          final file = File(clip.filePath);
                          if (await file.exists()) {
                            await file.delete();
                          }
                        } else {
                          _removedSavedPaths.add(clip.filePath);
                        }
                        if (mounted) {
                          setState(() => _clips.remove(clip));
                        }
                      },
                    ),
                  ),
                ),
              if (_errorText != null) ...[
                const SizedBox(height: 8),
                Text(
                  _errorText!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 12),
              FilledButton(
                onPressed: _saveProfile,
                child: const Text('Save Voice Profile'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
