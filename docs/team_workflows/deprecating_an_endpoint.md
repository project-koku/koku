# Deprecation of Endpoint Workflow

## Introduction

This document outlines the workflow to deprecate an endpoint within koku. Deprecating an endpoint involves several steps to ensure a smooth transition for users and to maintain the integrity of our services.

## Workflow

### Step 1: Impact Analysis

- **Objective:** Understand the impact of deprecating the endpoint on users, applications, and systems.
- **Actions:**
    - Identify users or services currently using the endpoint.
    - Analyze the extent of usage and dependencies on the endpoint.
    - Determine if there are alternative endpoints or methods to replace the deprecated one.
- **Example:**
    - When we deprecated the /settings endpoint we made a kibana dashboard to show us which users were still hitting the endpoint after the old UI was removed. That informed us that users were utilizes those urls in there workflows.

### Step 2: Create a Deprecation Timeline

- **Objective:** Define a timeline for the deprecation process.
- **Actions:**
    - Create a timeline that includes the announcement date, start of the deprecation period, and the official deprecation date.
    - Identify any milestones or checkpoints during the deprecation period.

### Step 3: Deprecation Implementation

- **Objective:** Prepare the code date for deprecation
- **Actions:**
1. Rename the api folder adding `deprecated_` to clearly identify no changes should be made in this directory moving forward.
2. Check for unleash flags within the folder and remove any unnecessary flags
3. Move any common functions that are no longer necessary into the deprecated_ folder. [Example](https://github.com/project-koku/koku/pull/4670/files#diff-9a4ece704604756b549b41d1e4b72e154ba290f2ba90cb032d270e5a9e190418L390-L440)
4. Create `deprecated_` versions of any common function still being used in the `deprecated_` folder, this prevents the need for backwards compatibility moving forward. [Example](https://github.com/project-koku/koku/pull/4670/files#diff-3f27604615bb126d6ad77ab747562f4fb028d4975a8cc2ab28a3967ea8f82a88R242-R266)
5. Add the deprecation wrapper
    - First update the view to include the `deprecation_datetime` & `sunset_datetime`. [Example](https://github.com/project-koku/koku/blob/9f46c8c3db6d856558ffdc9cf823ab6116590c67/koku/api/deprecated_settings/view.py#L20-L28)
    - Then import the `deprecate_view` wrapper, and wrap the view in the url definition to have the end of life headers added to the response.

### Step 4: Prepare the Sunset PR
- **Objective:** Prepare the code date for removal of the endpoint
- [Example](https://github.com/project-koku/koku/pull/4726)
- **Actions:**
    - After the deprecation PR is merged, create a new PR to remove the dead code. If you did the deprecation step correctly, all you should have to do is:
        1. Remove the `deprecate_` folder you created for the api
        2. Replace the `deprecate_view` wrapper with the `SunsetView`
        3. Update `koku/api/views.py` to remove old view `SettingsView`
    - Include the sunset date in the title and label the PR `on hold`, this indicates we are waiting for the upcoming date before it can be merged.
    - Create a reminder on the team calendar for when the PR needs to be moved into main.

## Step 5: Deprecation Notice
- **Objective** Create a notification for deprecating the endpoint.
- [Example](https://github.com/project-koku/koku/releases/tag/r.2023.10.06.0)
- **Actions:**
    - When the deprecation pull request goes to production create a deprecation notice for the release notes.
    - Identify and document alternative endpoints, methods, or solutions.
    - Create documentation and resources to guide users through the transition.

### Step 6: Documentation Update

- **Objective:** Update documentation and code to reflect the deprecation.
- **Actions:**
    - Review and update API documentation, user guides, and code examples.
    - Ensure that deprecated endpoint references are removed or replaced with alternatives.

### Step 7: Communication Plan
- **Objective:** Develop a plan to communicate the deprecation to affected users and stakeholders.
- **Actions:**
    - Prepare a clear and concise deprecation notice that explains the reason, timeline, and action steps for users.
    - Determine the communication channels (e.g., email, website, documentation) to reach users and stakeholders. This usually includes sending a email to `costmanagement-announce@redhat.com`
    - Establish a timeline for announcing the deprecation.

### Step 8: Deprecation Completion

- **Objective:** Officially complete the deprecation process.
- **Actions:**
    - Ensure that all users have transitioned to alternative solutions.
    - Confirm that the deprecated endpoint is no longer in use.
    - Document the completion of the deprecation process.

## Conclusion

Deprecating an endpoint is a strategic decision that requires careful planning, communication, and support for affected users. Following this workflow will help ensure a successful and smooth deprecation process.
