class Pocket {
  const Pocket({
    required this.id,
    required this.name,
    required this.purpose,
    required this.allocatedMinor,
    required this.spentMinor,
    required this.currency,
    required this.protected,
  });

  factory Pocket.fromJson(Map<String, dynamic> json) {
    return Pocket(
      id: json['id'] as String,
      name: json['name'] as String,
      purpose: json['purpose'] as String,
      allocatedMinor: json['allocated_minor'] as int,
      spentMinor: json['spent_minor'] as int? ?? 0,
      currency: (json['currency'] as String?) ?? 'CNGN',
      protected: json['protected'] as bool? ?? false,
    );
  }

  final String id;
  final String name;
  final String purpose;
  final int allocatedMinor;
  final int spentMinor;
  final String currency;
  final bool protected;

  /// Display-only — never sent back to the API, always recomputed.
  int get availableMinor => allocatedMinor - spentMinor;
}
