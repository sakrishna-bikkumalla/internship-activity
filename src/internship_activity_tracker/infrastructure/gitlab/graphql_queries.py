# All GitLab GraphQL query strings used by the application.
# Fields are chosen to exactly match the REST shapes consumed by existing UI/service layers.

# ── Phase 2: MRs ─────────────────────────────────────────────────────────────

GQL_USER_MRS_AUTHORED = """
query GetAuthoredMRs($username: String!, $after: String) {
  user(username: $username) {
    id
    username
    name
    avatarUrl
    webUrl
    authoredMergeRequests(first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        iid
        title
        description
        state
        webUrl
        createdAt
        mergedAt
        closedAt
        totalTimeSpent
        upvotes
        userNotesCount
        headPipeline { status }
        timelogs(first: 100) { nodes { timeSpent spentAt } }
        commits(first: 100) { nodes { title sha } }
        project { id fullPath }
      }
    }
  }
}
"""

GQL_USER_MRS_ASSIGNED = """
query GetAssignedMRs($username: String!, $after: String) {
  user(username: $username) {
    assignedMergeRequests(first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        iid
        title
        description
        state
        webUrl
        createdAt
        mergedAt
        closedAt
        totalTimeSpent
        upvotes
        userNotesCount
        headPipeline { status }
        project { id fullPath }
      }
    }
  }
}
"""

# ── Phase 2: Timelogs ─────────────────────────────────────────────────────────

GQL_USER_TIMELOGS = """
query GetUserTimelogs($username: String!, $startDate: Time, $endDate: Time, $after: String) {
  timelogs(username: $username, startDate: $startDate, endDate: $endDate, first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      timeSpent
      spentAt
      summary
      issue {
        id
        iid
        title
        webUrl
        state
        projectId
      }
      mergeRequest {
        id
        iid
        title
        webUrl
        state
        project { id fullPath }
      }
      project { id fullPath }
    }
  }
}
"""

# ── Phase 3: Issues ───────────────────────────────────────────────────────────

GQL_USER_ISSUES_AUTHORED = """
query GetAuthoredIssues($username: String!, $after: String) {
  issues(authorUsername: $username, first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      iid
      title
      description
      state
      webUrl
      createdAt
      closedAt
      totalTimeSpent
      projectId
      labels { nodes { title } }
      milestone { title }
      assignees { nodes { username } }
    }
  }
}
"""

GQL_USER_ISSUES_ASSIGNED = """
query GetAssignedIssues($username: String!, $after: String) {
  issues(assigneeUsernames: [$username], first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      iid
      title
      description
      state
      webUrl
      createdAt
      closedAt
      totalTimeSpent
      projectId
      labels { nodes { title } }
      milestone { title }
    }
  }
}
"""

# ── Phase 3: Groups + Projects ────────────────────────────────────────────────

GQL_USER_GROUPS = """
query GetUserGroups($username: String!) {
  user(username: $username) {
    groups(first: 100) {
      nodes {
        id
        name
        fullPath
        webUrl
        visibility
      }
    }
  }
}
"""

GQL_USER_PROJECTS = """
query GetUserProjects($username: String!) {
  user(username: $username) {
    contributedProjects(first: 100) {
      nodes {
        id
        name
        nameWithNamespace
        webUrl
        namespace { path }
      }
    }
    projectMemberships(first: 100) {
      nodes {
        project {
          id
          name
          nameWithNamespace
          webUrl
          namespace { path }
        }
      }
    }
  }
}
"""
