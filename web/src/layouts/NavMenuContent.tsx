import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import { Link as RouterLink, useLocation } from "react-router";
import { activeSection, projectIdFromPath, sectionPath } from "../app/sectionPaths";
import type { Project } from "../features/projects/projectsApi";
import { useGetProjectsQuery } from "../features/projects/projectsApi";
import { NAV_ITEMS } from "./navItems";

/** The most recently created project, or undefined while the list is loading or empty. */
function latestProject(projects: Project[] | undefined): Project | undefined {
  if (projects === undefined || projects.length === 0) {
    return undefined;
  }
  return projects.reduce((best, project) =>
    Date.parse(project.created_at) > Date.parse(best.created_at) ? project : best,
  );
}

/** The section nav shared by the permanent sidebar and the mobile drawer. */
export default function NavMenuContent({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useLocation();
  const { data: projects } = useGetProjectsQuery();
  // Links prefer the URL's own project; the list page has none, so fall back
  // to the newest project so Sources and Chat still lead somewhere.
  const targetId = projectIdFromPath(pathname) ?? latestProject(projects)?.id;
  const currentSection = activeSection(pathname);

  return (
    <Stack sx={{ flexGrow: 1, p: 1 }}>
      <List dense>
        {NAV_ITEMS.map((item) => {
          const href =
            item.section === "projects"
              ? "/projects"
              : item.section !== null && targetId !== undefined
                ? sectionPath(item.section, targetId)
                : null;
          const active = item.section !== null && item.section === currentSection;
          const Icon = item.icon;
          const content = (
            <>
              <ListItemIcon>
                <Icon />
              </ListItemIcon>
              <ListItemText primary={item.label} />
              {item.comingSoon === true && <Chip label="Coming soon" size="small" />}
            </>
          );
          return (
            <ListItem key={item.label} disablePadding sx={{ display: "block" }}>
              {href !== null && item.comingSoon !== true ? (
                <ListItemButton
                  component={RouterLink}
                  to={href}
                  onClick={onNavigate}
                  selected={active}
                  aria-current={active ? "page" : undefined}
                >
                  {content}
                </ListItemButton>
              ) : (
                <ListItemButton disabled>{content}</ListItemButton>
              )}
            </ListItem>
          );
        })}
      </List>
    </Stack>
  );
}
