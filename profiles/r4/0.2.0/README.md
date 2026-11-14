# Helseark source-assertion profiles 0.2.0

Additive history surface for FHIR R4 4.0.1. The original six 0.1.0
profiles remain frozen; Provenance 0.2.0 expands native target support.
Every scalar requires evidence and explicit human review. Unsupported elements
stay in the source, with a declared limitation, rather than being dropped.
See [clinical model and compatibility](../../../docs/reference/clinical-model.md#history-profile-compatibility-and-query).


- MedicationStatement: source-authored subject scope; native fields `identifier status statusReason category medicationCodeableConcept subject context effectiveDateTime effectivePeriod dateAsserted informationSource derivedFrom reasonCode reasonReference note dosage`. Timeline time: ('effectiveDateTime', 'effectivePeriod'). Preserve qualifiers, source evidence and unknown dates.

- MedicationRequest: source-authored subject scope; native fields `identifier status statusReason intent category priority doNotPerform reportedBoolean medicationCodeableConcept subject encounter supportingInformation authoredOn requester reasonCode reasonReference instantiatesCanonical instantiatesUri basedOn groupIdentifier courseOfTherapyType insurance note dosageInstruction dispenseRequest substitution priorPrescription detectedIssue eventHistory`. Timeline time: ('authoredOn',). Preserve qualifiers, source evidence and unknown dates.

- Condition: source-authored subject scope; native fields `identifier clinicalStatus verificationStatus category severity code bodySite subject encounter onsetDateTime onsetAge onsetPeriod onsetRange onsetString abatementDateTime abatementAge abatementPeriod abatementRange abatementString recordedDate recorder asserter stage evidence note`. Timeline time: ('onsetDateTime', 'onsetPeriod', 'onsetAge', 'onsetRange', 'onsetString'). Preserve qualifiers, source evidence and unknown dates.

- AllergyIntolerance: source-authored patient scope; native fields `identifier clinicalStatus verificationStatus type category criticality code patient encounter onsetDateTime onsetAge onsetPeriod onsetRange onsetString recordedDate recorder asserter lastOccurrence note reaction`. Timeline time: ('onsetDateTime', 'onsetPeriod', 'onsetAge', 'onsetRange', 'onsetString'). Preserve qualifiers, source evidence and unknown dates.

- Immunization: source-authored patient scope; native fields `identifier status statusReason vaccineCode patient encounter occurrenceDateTime occurrenceString recorded primarySource reportOrigin location manufacturer lotNumber expirationDate site route doseQuantity performer note reasonCode reasonReference isSubpotent subpotentReason education programEligibility fundingSource reaction protocolApplied`. Timeline time: ('occurrenceDateTime', 'occurrenceString'). Preserve qualifiers, source evidence and unknown dates.

- Procedure: source-authored subject scope; native fields `identifier instantiatesCanonical instantiatesUri basedOn partOf status statusReason category code subject encounter performedDateTime performedPeriod performedString performedAge performedRange recorder asserter performer location reasonCode reasonReference bodySite outcome report complication complicationDetail followUp note focalDevice usedReference usedCode`. Timeline time: ('performedDateTime', 'performedPeriod', 'performedString', 'performedAge', 'performedRange'). Preserve qualifiers, source evidence and unknown dates.

- Encounter: source-authored subject scope; native fields `identifier status statusHistory class classHistory type serviceType priority subject episodeOfCare basedOn participant appointment period length reasonCode reasonReference diagnosis account hospitalization location serviceProvider partOf`. Timeline time: ('period',). Preserve qualifiers, source evidence and unknown dates.

- FamilyMemberHistory: source-authored patient scope; native fields `identifier instantiatesCanonical instantiatesUri status dataAbsentReason patient date name relationship sex bornPeriod bornDate bornString ageAge ageRange ageString estimatedAge deceasedBoolean deceasedAge deceasedRange deceasedDate deceasedString reasonCode reasonReference note condition`. Timeline time: ('date',). Preserve qualifiers, source evidence and unknown dates.
