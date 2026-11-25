import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:myvoice_ai/data/models/voice_profile.dart';
import 'package:myvoice_ai/data/providers/app_providers.dart';
import 'package:myvoice_ai/features/profiles/profile_editor_sheet.dart';

class ProfilesScreen extends ConsumerWidget {
  const ProfilesScreen({super.key});

  Future<void> _openEditor(BuildContext context, {VoiceProfile? profile}) async {
    await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => ProfileEditorSheet(existingProfile: profile),
    );
  }

  Future<void> _confirmDelete(
    BuildContext context,
    WidgetRef ref,
    VoiceProfile profile,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Voice Profile?'),
        content: Text(
          'This permanently deletes "${profile.name}" and its ${profile.clips.length} '
          'voice sample file(s) from private device storage.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed == true) {
      final player = ref.read(audioPlayerProvider);
      for (final clip in profile.clips) {
        await player.stopIfActive(clip.filePath);
      }
      await ref.read(appStateProvider.notifier).deleteProfile(profile);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(appStateProvider);
    final profiles = state.profiles;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Voice Profiles'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: FilledButton.icon(
              onPressed: () => _openEditor(context),
              icon: const Icon(Icons.add),
              label: const Text('New Profile'),
            ),
          ),
        ],
      ),
      body: profiles.isEmpty
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.record_voice_over_outlined,
                        size: 64, color: Theme.of(context).colorScheme.primary),
                    const SizedBox(height: 12),
                    Text('No Voice Profiles Yet', style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 8),
                    const Text(
                      'Record 6–15s clean clips (Neutral, Conversational, Expressive) for Tier 1 '
                      'Instant Zero-Shot cloning, or link a Tier 2 fine-tuned checkpoint.',
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      onPressed: () => _openEditor(context),
                      icon: const Icon(Icons.mic),
                      label: const Text('Create Voice Profile'),
                    ),
                  ],
                ),
              ),
            )
          : ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: profiles.length,
              separatorBuilder: (_, __) => const SizedBox(height: 12),
              itemBuilder: (context, index) {
                final profile = profiles[index];
                final styles = profile.clips.map((c) => c.style.label).toSet().join(', ');
                return Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.all(16),
                    leading: CircleAvatar(
                      child: Icon(
                        profile.profileType == ProfileType.trainedModel
                            ? Icons.auto_awesome
                            : Icons.graphic_eq,
                      ),
                    ),
                    title: Text(profile.name),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 4),
                        Text(profile.profileType.label),
                        Text(
                          '${profile.clips.length} clip(s)${styles.isEmpty ? '' : ' • $styles'}',
                        ),
                      ],
                    ),
                    trailing: PopupMenuButton<String>(
                      onSelected: (action) {
                        if (action == 'edit') {
                          _openEditor(context, profile: profile);
                        } else if (action == 'delete') {
                          _confirmDelete(context, ref, profile);
                        }
                      },
                      itemBuilder: (_) => const [
                        PopupMenuItem(value: 'edit', child: Text('Edit')),
                        PopupMenuItem(value: 'delete', child: Text('Delete Permanently')),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}
