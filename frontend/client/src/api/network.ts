/** DRISHYAM local integration: case-scoped criminal-network read models and relationship review.
 *
 * Every ranked entity arrives with `why` and `caveat` from the server. The interface must render
 * both: a centrality score shown on its own invites the reading that the system is scoring people
 * for criminality, which it is not doing.
 */
import { apiClient } from "./client";

export type NetworkOverviewRecord = { entities: number; relationships: number; communities: number; bridges: number; isolated_entities: number; analytics_version: string };
export type ImportantEntityRecord = { entity_id: string; label: string; entity_type: string; metric: string; score: number; rank: number; connections: number; supporting_evidence_count: number; communities_linked: number; is_bridge: boolean; why: string; caveat: string };
export type NetworkEndpointRecord = { id: string; label: string | null; entity_type?: string | null; type?: string | null };
export type NetworkEdgeRecord = { subject_entity_id: string; object_entity_id: string; relation_types: string[]; confidence: number; observations: number; supporting_evidence_count: number };
export type BridgeRecord = { subject: NetworkEndpointRecord; object: NetworkEndpointRecord; relation_types: string[]; confidence: number; observations: number; supporting_evidence_count: number; why: string; caveat: string };
export type CommunityRecord = { community_id: number; size: number; supporting_evidence_count: number; members: NetworkEndpointRecord[]; caveat: string };
export type NetworkPathRecord = { found: boolean; reason: string | null; nodes: NetworkEndpointRecord[]; edges: NetworkEdgeRecord[]; weakest_link_confidence: number | null; caveat: string | null };
export type NetworkSubgraphRecord = { center: string | null; hops: number | null; nodes: Array<{ id: string; label: string; entity_type: string }>; edges: NetworkEdgeRecord[]; truncated: boolean };

export type EntityRelationRecord = { id: string; relation_type: string; directed: boolean; basis: string; subject: { id: string; label: string | null; type: string | null }; object: { id: string; label: string | null; type: string | null }; source_evidence_id: string; source_record_id: string | null; source_reference: Record<string, unknown>; observed_at: string | null; time_precision: string; confidence: number; verification_status: string; review_note: string | null; created_at: string };
export type EntityRelationPage = { items: EntityRelationRecord[]; total: number; limit: number; offset: number };
export type EntityRelationSummaryRecord = { relation_type: string; meaning: string; directed: boolean; subject: { id: string; label: string | null; type: string | null }; object: { id: string; label: string | null; type: string | null }; observation_ids: string[]; observation_count: number; evidence_ids: string[]; supporting_evidence_count: number; bases: string[]; confidence: number; verification_status: string; first_observed_at: string | null; last_observed_at: string | null };

export type ImportanceMetric = "betweenness_centrality" | "degree_centrality" | "eigenvector_centrality";

const base = (caseId: string) => `/cases/${caseId}/grounded`;

export async function getNetworkOverview(caseId: string): Promise<NetworkOverviewRecord> { return (await apiClient.get(`${base(caseId)}/network/overview`)).data; }
export async function getImportantEntities(caseId: string, params: { metric?: ImportanceMetric; entity_type?: string; min_confidence?: number; verified_only?: boolean; limit?: number } = {}): Promise<ImportantEntityRecord[]> { return (await apiClient.get(`${base(caseId)}/network/important`, { params })).data; }
export async function getNetworkBridges(caseId: string, minConfidence = 0): Promise<BridgeRecord[]> { return (await apiClient.get(`${base(caseId)}/network/bridges`, { params: { min_confidence: minConfidence } })).data; }
export async function getNetworkCommunities(caseId: string, minConfidence = 0): Promise<CommunityRecord[]> { return (await apiClient.get(`${base(caseId)}/network/communities`, { params: { min_confidence: minConfidence } })).data; }
export async function getNetworkPath(caseId: string, sourceEntityId: string, targetEntityId: string): Promise<NetworkPathRecord> { return (await apiClient.get(`${base(caseId)}/network/path`, { params: { source_entity_id: sourceEntityId, target_entity_id: targetEntityId } })).data; }
export async function getNetworkSubgraph(caseId: string, entityId: string, hops = 1): Promise<NetworkSubgraphRecord> { return (await apiClient.get(`${base(caseId)}/network/subgraph`, { params: { entity_id: entityId, hops } })).data; }

export async function getEntityRelations(caseId: string, params: { relation_type?: string; entity_id?: string; verification_status?: string; limit?: number; offset?: number } = {}): Promise<EntityRelationPage> { return (await apiClient.get(`${base(caseId)}/entity-relations`, { params })).data; }
export async function getEntityRelationSummary(caseId: string): Promise<EntityRelationSummaryRecord[]> { return (await apiClient.get(`${base(caseId)}/entity-relations/summary`)).data; }
export async function reviewEntityRelation(caseId: string, relationId: string, action: "confirm_relationship" | "reject_relationship", reason?: string): Promise<EntityRelationRecord> { return (await apiClient.post(`${base(caseId)}/entity-relations/${relationId}/review`, { action, reason })).data; }

/** One statement from an entity summary, and the evidence it was read from. */
export type EntitySentence = { text: string; evidence: string | null; place: string | null; basis: string | null };

export type EntitySummaryRecord = {
  entity_id: string;
  label: string;
  entity_type: string;
  sentences: EntitySentence[];
  roles: string[];
  source_count: number;
  relation_count: number;
  caveat: string;
  summary_version: string;
};

/**
 * Who an identity is, assembled by the server from stored rows. Nothing is generated, so every
 * sentence carries its source and no part of the case leaves the machine to produce it.
 */
export async function getEntitySummary(caseId: string, entityId: string): Promise<EntitySummaryRecord> {
  return (await apiClient.get(`${base(caseId)}/entities/${entityId}/summary`)).data;
}

/** One way the identity was written down, and where it was written that way. */
export type EntityAlias = { value: string; evidence: string | null; field_name: string | null; stated_role: string | null };

export type EntityAppearance = {
  occurrence_id: string; evidence_id: string; evidence: string | null; place: string | null;
  observed_value: string; field_name: string | null; stated_role: string | null;
  confidence: number; source_reference: Record<string, unknown>;
};

export type EntityConnection = {
  relation_id: string; relation_type: string; meaning: string; directed: boolean; outgoing: boolean;
  other_id: string; other_label: string; other_type: string;
  evidence_id: string; evidence: string | null; place: string | null;
  observed_at: string | null; time_precision: string; confidence: number;
  verification_status: string; source_reference: Record<string, unknown>;
};

export type EntityMoment = {
  when: string; precision: string; statement: string;
  evidence_id: string; evidence: string | null; place: string | null; source_reference: Record<string, unknown>;
};

export type EntityOtherCase = { case_id: string; case_number: string; title: string; status: string; written_as: string };

export type EntityProfileRecord = {
  entity_id: string; label: string; entity_type: string; normalized_value: string;
  aliases: EntityAlias[]; appearances: EntityAppearance[]; connections: EntityConnection[];
  timeline: EntityMoment[]; other_cases: EntityOtherCase[]; roles: string[]; unreviewed: number;
  alias_caveat: string; other_case_caveat: string; profile_version: string;
};

/** Everything this case records about one identity. Assembled by the server from stored rows. */
export async function getEntityProfile(caseId: string, entityId: string): Promise<EntityProfileRecord> {
  return (await apiClient.get(`${base(caseId)}/entities/${entityId}/profile`)).data;
}

/** How the case's contact record sits around the declared incident: `app/services/temporal.py`. */
export type CaseChronology = { incident_window_declared: boolean; incident_start: string | null; incident_end: string | null; contacts_placed: Record<string, number>; contacts_without_established_time: boolean; temporal_version: string };

export async function getChronology(caseId: string): Promise<CaseChronology> { return (await apiClient.get(`/cases/${caseId}/grounded/temporal/chronology`)).data; }

/** Whether a force this reader cannot see is already looking for the same identity. */
export type ElsewhereMatch = { case_reference: string; contact: string; published_at: string; your_identity: string };
export type IdentityElsewhere = { available: boolean; matches: ElsewhereMatch[]; note: string; caveat: string };

/** Asking is itself an access event; the server records it. */
export async function getIdentityElsewhere(caseId: string, entityId: string): Promise<IdentityElsewhere> {
  return (await apiClient.get(`${base(caseId)}/entities/${entityId}/elsewhere`)).data;
}

/** What the national record of registered cases holds about an identity. A different source from
 * the shared ledger, and a different question: the ledger reports a live case another force is
 * working; this reports cases already registered, with what became of each. */
export type PriorRecordEntry = {
  record_reference: string;
  police_station: string;
  district: string | null;
  sections: string[];
  registered_on: string;
  disposal: string;
  disposal_reading: string;
  disposal_state: "open" | "closed" | "unknown";
  disposal_on: string | null;
  subject_name: string | null;
  contact_officer: string | null;
  source: string;
};
export type PriorRecordLookup = { identity: string; matched_on: string | null; entries: PriorRecordEntry[]; statement: string; caveat: string; version: string };

/** Looking somebody up in a criminal record is recorded, whatever it returns. */
export async function getPriorRecord(caseId: string, entityId: string): Promise<PriorRecordLookup> {
  return (await apiClient.get(`${base(caseId)}/entities/${entityId}/prior-record`)).data;
}
