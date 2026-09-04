import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/app_colors.dart';
import '../../app/theme/app_spacing.dart';
import '../../app/theme/app_typography.dart';
import '../../providers/goal_provider.dart';

class AssistantScreen extends ConsumerStatefulWidget {
  const AssistantScreen({super.key});

  @override
  ConsumerState<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends ConsumerState<AssistantScreen> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _createPlan() {
    final text = _controller.text.trim();

    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Tell FlowPilot what you want to do with your money.'),
        ),
      );
      return;
    }

void _createPlan() {
  final text = _controller.text.trim();

  if (text.isEmpty) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Tell FlowPilot what you want to do with your money.'),
      ),
    );
    return;
  }

  context.push('/planning');
}
  }

  void _useDemoPrompt() {
    setState(() {
      _controller.text =
          'I have ₦300,000 available. Help me move ₦100,000 to my bank so it is safely set aside.';
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('FlowPilot'),
            Text(
              'AI Financial Copilot',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.secondaryText,
                fontWeight: FontWeight.w400,
              ),
            ),
          ],
        ),
        backgroundColor: AppColors.background,
        elevation: 0,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(AppSpacing.lg),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: AppColors.border),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.auto_awesome,
                      color: AppColors.accent,
                      size: 30,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'What would you like to do?',
                      style: AppTypography.title,
                    ),
                    const SizedBox(height: 8),
                Text(
  'Describe your financial goal in plain language. '
  'FlowPilot will create a plan for you to review.',
  style: const TextStyle(
    color: AppColors.secondaryText,
    fontSize: 14,
  ),
),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
              TextField(
                controller: _controller,
                minLines: 5,
                maxLines: 8,
                style: const TextStyle(color: AppColors.primaryText),
                decoration: InputDecoration(
                  hintText:
                      'Example: Help me move ₦100,000 to my bank...',
                  hintStyle: const TextStyle(
                    color: AppColors.secondaryText,
                  ),
                  filled: true,
                  fillColor: AppColors.surface,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(
                      color: AppColors.border,
                    ),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(
                      color: AppColors.border,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              TextButton(
                onPressed: _useDemoPrompt,
                child: const Text('Use demo request'),
              ),
              const SizedBox(height: AppSpacing.lg),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton(
  onPressed: _createPlan,
  style: ElevatedButton.styleFrom(
    backgroundColor: AppColors.accent,
    foregroundColor: Colors.black,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(12),
    ),
  ),
  child: const Text(
    'Create Plan',
    style: TextStyle(
      fontWeight: FontWeight.w700,
      fontSize: 16,
    ),
  ),
),
              ),
              const SizedBox(height: AppSpacing.lg),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppColors.elevated,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.shield_outlined,
                      color: AppColors.success,
                    ),
                    SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'FlowPilot never executes transactions automatically. '
                        'You review and approve every action before it is submitted.',
                        style: TextStyle(
                          color: AppColors.secondaryText,
                          fontSize: 13,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}