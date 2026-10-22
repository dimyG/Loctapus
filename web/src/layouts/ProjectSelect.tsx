import Avatar from "@mui/material/Avatar";
import MenuItem from "@mui/material/MenuItem";
import Select, { selectClasses } from "@mui/material/Select";
import type { SelectChangeEvent } from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useLocation, useNavigate } from "react-router";
import { projectIdFromPath, sectionPath, switchProjectPath } from "../app/sectionPaths";
import type { Project } from "../features/projects/projectsApi";
import { useGetProjectsQuery } from "../features/projects/projectsApi";
import { gray } from "../theme/themePrimitives";

/** Projects newest first, so the freshest project leads the list. */
function sortNewestFirst(projects: Project[]): Project[] {
  return [...projects].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

/**
 * The topbar project picker. The URL is the source of truth: the select
 * shows the URL's project whenever it is in the loaded list, and a
 * placeholder otherwise (no project in the URL, still loading, or a stale
 * id), so the Select never carries an out-of-range value. Choosing a
 * project swaps the URL's project segment and keeps any deep section.
 */
export default function ProjectSelect() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { data: projects } = useGetProjectsQuery();
  const urlProjectId = projectIdFromPath(pathname);
  const sorted = projects !== undefined ? sortNewestFirst(projects) : [];
  const noProjects = projects !== undefined && sorted.length === 0;
  const value =
    urlProjectId !== null && sorted.some((project) => project.id === urlProjectId)
      ? urlProjectId
      : "";

  /** Swaps the project in place, or lands on sources when the URL has no project. */
  function handleChange(event: SelectChangeEvent) {
    const newProjectId = event.target.value;
    navigate(
      urlProjectId !== null
        ? switchProjectPath(pathname, newProjectId)
        : sectionPath("sources", newProjectId),
    );
  }

  return (
    <Select
      value={value}
      onChange={handleChange}
      displayEmpty
      disabled={noProjects}
      inputProps={{ "aria-label": "Project" }}
      sx={{
        maxHeight: 56,
        width: 215,
        "&.MuiList-root": {
          p: "8px",
        },
        [`& .${selectClasses.select}`]: {
          display: "flex",
          alignItems: "center",
          gap: "2px",
          pl: 1,
        },
      }}
      renderValue={(selected) => {
        if (selected === "") {
          return noProjects ? "No projects" : "Select project";
        }
        const project = sorted.find((candidate) => candidate.id === selected);
        if (project === undefined) {
          return "";
        }
        // The template's two-line selector: leading avatar initial, then the
        // name over a "Project" caption; the 56px cap above keeps it centered.
        return (
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Avatar sx={{ width: 28, height: 28, fontSize: 14 }}>{project.name.charAt(0)}</Avatar>
            <Stack>
              <Typography variant="body2">{project.name}</Typography>
              {/* Dark mode's text.secondary lands too close to the white name
                  at caption size, so dim it to gray[500] there only. */}
              <Typography
                variant="caption"
                sx={(theme) => ({
                  color: "text.secondary",
                  ...theme.applyStyles("dark", { color: gray[500] }),
                })}
              >
                Project
              </Typography>
            </Stack>
          </Stack>
        );
      }}
    >
      {sorted.map((project) => (
        <MenuItem key={project.id} value={project.id}>
          {project.name}
        </MenuItem>
      ))}
    </Select>
  );
}
