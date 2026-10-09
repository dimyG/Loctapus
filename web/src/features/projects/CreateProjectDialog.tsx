import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { skipToken } from "@reduxjs/toolkit/query";
import type { FormEvent } from "react";
import { useState } from "react";
import { getErrorMessage } from "../../app/api";
import { useGetWorkspaceTeamsQuery } from "../workspaces/teamsApi";
import { useGetWorkspacesQuery } from "../workspaces/workspacesApi";
import { useCreateProjectMutation } from "./projectsApi";

/** The create-project form inside a dialog, with the workspace->team picker. */
export default function CreateProjectDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { data: workspaces } = useGetWorkspacesQuery();
  // Explicit picks override the derived defaults (first option once loaded).
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | undefined>(undefined);
  const effectiveWorkspaceId = selectedWorkspaceId ?? workspaces?.[0]?.id;
  const { data: teams, error: teamsError } = useGetWorkspaceTeamsQuery(
    effectiveWorkspaceId ?? skipToken,
  );
  const [teamOverride, setTeamOverride] = useState<string | undefined>(undefined);
  const effectiveTeamId = teamOverride ?? teams?.[0]?.id;
  const [createProject] = useCreateProjectMutation();
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  function handleWorkspaceChange(id: string) {
    setSelectedWorkspaceId(id);
    setTeamOverride(undefined);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (effectiveTeamId === undefined) {
      setDialogError("Pick a team for the project.");
      return;
    }
    setPending(true);
    setDialogError(null);
    try {
      await createProject({ name, team_id: effectiveTeamId }).unwrap();
      onClose();
    } catch (e) {
      setDialogError(getErrorMessage(e));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle sx={{ fontWeight: 600 }}>Create project</DialogTitle>
      <form onSubmit={handleSubmit} noValidate>
        <DialogContent>
          <Stack spacing={2}>
            {teamsError !== undefined ? (
              <Alert role="alert" severity="error">
                {getErrorMessage(teamsError)}
              </Alert>
            ) : (
              dialogError !== null && (
                <Alert role="alert" severity="error">
                  {dialogError}
                </Alert>
              )
            )}
            <TextField
              label="Name"
              name="name"
              required
              fullWidth
              disabled={pending}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <TextField
              select
              label="Workspace"
              name="workspace"
              required
              fullWidth
              disabled={pending || workspaces === undefined}
              value={effectiveWorkspaceId ?? ""}
              onChange={(event) => handleWorkspaceChange(event.target.value)}
            >
              {(workspaces ?? []).map((workspace) => (
                <MenuItem key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Team"
              name="team"
              required
              fullWidth
              disabled={pending || teams === undefined}
              value={effectiveTeamId ?? ""}
              onChange={(event) => setTeamOverride(event.target.value)}
            >
              {(teams ?? []).map((team) => (
                <MenuItem key={team.id} value={team.id}>
                  {team.name}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={pending || effectiveTeamId === undefined}
          >
            Create
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
