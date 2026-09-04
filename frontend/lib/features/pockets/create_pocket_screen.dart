import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import 'pockets_provider.dart';

class CreatePocketScreen extends ConsumerStatefulWidget {
  const CreatePocketScreen({super.key});

  @override
  ConsumerState<CreatePocketScreen> createState() => _CreatePocketScreenState();
}

class _CreatePocketScreenState extends ConsumerState<CreatePocketScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _purposeController = TextEditingController();
  final _amountController = TextEditingController(); // whole-currency units, converted to minor on submit
  bool _protected = false;
  bool _isSubmitting = false;

  @override
  void dispose() {
    _nameController.dispose();
    _purposeController.dispose();
    _amountController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isSubmitting = true);
    try {
      // User enters whole-unit currency (e.g. 300000.00); the API wants
      // integer minor units. Convert here, at the UI boundary only.
      final majorValue = double.parse(_amountController.text.trim());
      final allocatedMinor = (majorValue * 100).round();

      await ref.read(pocketsProvider.notifier).createPocket(
            name: _nameController.text.trim(),
            purpose: _purposeController.text.trim(),
            allocatedMinor: allocatedMinor,
            protected: _protected,
          );
      if (!mounted) return;
      BMoniToastOverlay.showSuccess(context: context, message: 'Pocket created');
      context.pop();
    } on ApiException catch (e) {
      if (!mounted) return;
      final message = e.isConflict ? 'A pocket with this name already exists.' : e.message;
      BMoniToastOverlay.showError(context: context, message: message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const CustomAppBar(title: 'Create pocket', showBackButton: true),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                BMoniTextFormField.filled(
                  label: 'Name',
                  hintText: 'Emergency Fund',
                  controller: _nameController,
                  validator: (value) =>
                      (value == null || value.trim().length < 2) ? 'Enter a name' : null,
                ),
                const SizedBox(height: 16),
                BMoniTextFormField.filled(
                  label: 'Purpose',
                  hintText: 'Unexpected expenses',
                  controller: _purposeController,
                  validator: (value) =>
                      (value == null || value.trim().length < 2) ? 'Enter a purpose' : null,
                ),
                const SizedBox(height: 16),
                BMoniTextFormField.filled(
                  label: 'Amount (CNGN)',
                  hintText: '300000.00',
                  controller: _amountController,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  validator: (value) {
                    final parsed = double.tryParse(value ?? '');
                    if (parsed == null || parsed < 0) return 'Enter a valid amount';
                    return null;
                  },
                ),
                const SizedBox(height: 16),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Protected'),
                  subtitle: const Text('Protected pockets can\'t fund Currency Shield conversions'),
                  value: _protected,
                  onChanged: (value) => setState(() => _protected = value),
                ),
                const SizedBox(height: 24),
                BMoniButton.primary(
                  onPressed: _isSubmitting ? null : _submit,
                  text: 'Create pocket',
                  isLoading: _isSubmitting,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
