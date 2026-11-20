# Which factors should go into the dining hall decision trees?
# Input: dining_hall_mock_data.xlsx (put it in your working directory)
required_packages <- c("readxl", "dplyr", "ggplot2", "rpart", "rpart.plot", "randomForest")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_packages) > 0) {
  install.packages(missing_packages, repos = "https://cloud.r-project.org")
}

library(readxl)
library(dplyr)
library(ggplot2)
library(rpart)
library(rpart.plot)
library(randomForest)

set.seed(42)
file <- "dining_hall_mock_data.xlsx"
dir.create("plots", showWarnings = FALSE)

save_plot <- function(p, name) {
  print(p)
  ggsave(file.path("plots", paste0(name, ".png")), p, width = 8, height = 5, dpi = 150)
}

# Share of variance in y explained by a grouping factor x (0 to 1)
eta_sq <- function(y, x) {
  ss <- summary(aov(y ~ factor(x)))[[1]][["Sum Sq"]]
  ss[1] / sum(ss)
}

# Tree importance as % of total
tree_imp <- function(tree) {
  v <- tree$variable.importance
  sort(round(100 * v / sum(v), 1), decreasing = TRUE)
}

# ---------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------
att_raw   <- read_excel(file, sheet = "table1_attendance")
dishes    <- read_excel(file, sheet = "table2_dishes")
purchases <- read_excel(file, sheet = "table3_ingredients")

day_levels <- c("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
per_levels <- c("morning", "afternoon", "evening")

att_raw <- att_raw %>% mutate(date = as.Date(date))
term_start <- min(att_raw$date)

attendance <- att_raw %>%
  mutate(
    day         = factor(day, levels = day_levels),
    time_period = factor(time_period, levels = per_levels),
    is_weekend  = factor(day %in% c("Saturday", "Sunday")),
    week        = as.integer(as.numeric(date - term_start) %/% 7) + 1
  )

# ---------------------------------------------------------------
# 2. TREE 1: what drives the number of students?
# ---------------------------------------------------------------
p1 <- ggplot(attendance, aes(time_period, number_of_students, fill = time_period)) +
  geom_boxplot(show.legend = FALSE) +
  labs(title = "Turnout by time period", x = NULL, y = "Students")
save_plot(p1, "turnout_by_period")

p2 <- ggplot(attendance, aes(day, number_of_students, fill = day)) +
  geom_boxplot(show.legend = FALSE) +
  labs(title = "Turnout by day of week", x = NULL, y = "Students")
save_plot(p2, "turnout_by_day")

heat <- attendance %>%
  group_by(day, time_period) %>%
  summarise(avg = mean(number_of_students), .groups = "drop")
p3 <- ggplot(heat, aes(time_period, day, fill = avg)) +
  geom_tile() +
  geom_text(aes(label = round(avg)), colour = "white") +
  scale_y_discrete(limits = rev(day_levels)) +
  labs(title = "Average turnout: day x time period", x = NULL, y = NULL, fill = "Students")
save_plot(p3, "turnout_heatmap")

p4 <- ggplot(attendance, aes(week, number_of_students, colour = time_period)) +
  stat_summary(fun = mean, geom = "line") +
  stat_summary(fun = mean, geom = "point") +
  labs(title = "Average turnout by week of term", x = "Week", y = "Students", colour = NULL)
save_plot(p4, "turnout_by_week")

att_effect <- data.frame(
  factor = c("time_period", "day", "is_weekend", "week"),
  eta_sq = c(
    eta_sq(attendance$number_of_students, attendance$time_period),
    eta_sq(attendance$number_of_students, attendance$day),
    eta_sq(attendance$number_of_students, attendance$is_weekend),
    eta_sq(attendance$number_of_students, attendance$week)
  )
) %>% arrange(desc(eta_sq))
cat("\n=== Tree 1: variance in turnout explained by each factor (eta squared) ===\n")
print(att_effect)

tree1 <- rpart(
  number_of_students ~ day + time_period + is_weekend + week,
  data = attendance, method = "anova",
  control = rpart.control(cp = 0.01, minsplit = 10)
)
cat("\n=== Tree 1: rpart variable importance (%) ===\n")
print(tree_imp(tree1))
png("plots/tree1_turnout.png", width = 1000, height = 650, res = 120)
rpart.plot(tree1, main = "Tree 1: predicted turnout", type = 4, extra = 101)
dev.off()
rpart.plot(tree1, main = "Tree 1: predicted turnout", type = 4, extra = 101)

rf1 <- randomForest(
  number_of_students ~ day + time_period + is_weekend + week,
  data = attendance, importance = TRUE, ntree = 500
)
cat("\n=== Tree 1: random forest importance (%IncMSE) ===\n")
print(round(importance(rf1, type = 1), 1))
write.csv(
  data.frame(
    model = "turnout",
    factor = rownames(importance(rf1, type = 1)),
    importance_pct = round(importance(rf1, type = 1)[, 1], 1)
  ),
  "r_turnout_tree_importance.csv",
  row.names = FALSE
)

# ---------------------------------------------------------------
# 3. TREE 2: what drives leftovers per dish?
# ---------------------------------------------------------------
dishes <- dishes %>%
  mutate(date = as.Date(date), time_period = time_of_day_served) %>%
  left_join(
    att_raw %>% select(date, time_period, number_of_students, day),
    by = c("date", "time_period")
  ) %>%
  mutate(
    pct_left          = leftover / amount_made,
    made_per_student  = amount_made / number_of_students,
    is_weekend        = factor(day %in% c("Saturday", "Sunday")),
    dish              = factor(dish),
    time_of_day_served = factor(time_of_day_served, levels = per_levels)
  )

dish_avg <- dishes %>%
  group_by(dish) %>%
  summarise(avg_pct_left = mean(pct_left), n = n(), .groups = "drop") %>%
  arrange(desc(avg_pct_left))
cat("\n=== Average share left over, by dish ===\n")
print(dish_avg)

p5 <- ggplot(dish_avg, aes(reorder(dish, avg_pct_left), avg_pct_left)) +
  geom_col(fill = "#534AB7") +
  coord_flip() +
  scale_y_continuous(labels = scales::percent) +
  labs(title = "Average share of dish left over", x = NULL, y = "Left over")
save_plot(p5, "leftover_by_dish")

p6 <- ggplot(dishes, aes(made_per_student, pct_left, colour = time_of_day_served)) +
  geom_point(alpha = 0.72, size = 2) +
  geom_smooth(method = "lm", se = FALSE, linewidth = 1) +
  scale_y_continuous(labels = scales::percent) +
  scale_colour_manual(
    values = c(morning = "#E69F00", afternoon = "#009E73", evening = "#0072B2"),
    limits = per_levels
  ) +
  labs(title = "Leftovers vs portions made per student",
       x = "Portions made per student", y = "Left over", colour = "Time of day")
save_plot(p6, "leftover_vs_made_per_student")

period_leftovers <- dishes %>%
  group_by(time_of_day_served) %>%
  summarise(avg_pct_left = mean(pct_left), .groups = "drop")

p6_period <- ggplot(dishes, aes(time_of_day_served, pct_left,
                                fill = time_of_day_served)) +
  geom_boxplot(outlier.alpha = 0.45, width = 0.65, show.legend = FALSE) +
  geom_point(data = period_leftovers, aes(time_of_day_served, avg_pct_left),
             shape = 18, size = 5, colour = "#252525", inherit.aes = FALSE) +
  scale_fill_manual(values = c(morning = "#E69F00",
                               afternoon = "#009E73",
                               evening = "#0072B2"),
                    limits = per_levels) +
  scale_y_continuous(labels = scales::percent) +
  labs(title = "Leftover share by time of day",
       subtitle = "Diamond marks the average for each time period",
       x = NULL, y = "Share left over")
save_plot(p6_period, "leftover_by_time_of_day")

dishes <- dishes %>%
  mutate(consumed = amount_made - leftover,
         pct_consumed = consumed / amount_made)

consumed_by_dish <- dishes %>%
  group_by(dish) %>%
  summarise(
    total_consumed = sum(consumed),
    avg_pct_consumed = mean(pct_consumed),
    .groups = "drop"
  ) %>%
  arrange(desc(total_consumed))

p8 <- ggplot(consumed_by_dish,
             aes(reorder(dish, total_consumed), total_consumed,
                 fill = avg_pct_consumed)) +
  geom_col() +
  geom_text(aes(label = paste0(round(avg_pct_consumed * 100), "%")),
            hjust = -0.08, size = 3.2) +
  coord_flip(clip = "off") +
  scale_fill_gradient(low = "#A7D8F0", high = "#005A9C",
                      labels = scales::percent) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.18))) +
  labs(title = "Most consumed dishes",
       subtitle = "Label shows average share consumed",
       x = NULL, y = "Portions consumed",
       fill = "Average consumed")
save_plot(p8, "most_consumed_dishes")

dish_effect <- data.frame(
  factor = c("dish", "time_of_day_served", "is_weekend"),
  eta_sq = c(
    eta_sq(dishes$pct_left, dishes$dish),
    eta_sq(dishes$pct_left, dishes$time_of_day_served),
    eta_sq(dishes$pct_left, dishes$is_weekend)
  )
) %>% arrange(desc(eta_sq))
cat("\n=== Tree 2: variance in leftover share explained (eta squared) ===\n")
print(dish_effect)
cat("\nCorrelation of leftover share with number_of_students:",
    round(cor(dishes$pct_left, dishes$number_of_students), 2), "\n")
cat("Correlation of leftover share with made_per_student:",
    round(cor(dishes$pct_left, dishes$made_per_student), 2), "\n")

tree2 <- rpart(
  pct_left ~ dish + time_of_day_served + number_of_students + made_per_student + is_weekend,
  data = dishes, method = "anova",
  control = rpart.control(cp = 0.01, minsplit = 10)
)
cat("\n=== Tree 2: rpart variable importance (%) ===\n")
print(tree_imp(tree2))
png("plots/tree2_leftovers.png", width = 1100, height = 700, res = 120)
rpart.plot(tree2, main = "Tree 2: share of dish left over", type = 4, extra = 101)
dev.off()
rpart.plot(tree2, main = "Tree 2: share of dish left over", type = 4, extra = 101)

rf2 <- randomForest(
  pct_left ~ dish + time_of_day_served + number_of_students + made_per_student + is_weekend,
  data = dishes, importance = TRUE, ntree = 500
)
cat("\n=== Tree 2: random forest importance (%IncMSE) ===\n")
print(round(importance(rf2, type = 1), 1))
write.csv(
  data.frame(
    model = "leftovers",
    factor = rownames(importance(rf2, type = 1)),
    importance_pct = round(importance(rf2, type = 1)[, 1], 1)
  ),
  "r_leftover_tree_importance.csv",
  row.names = FALSE
)

# ---------------------------------------------------------------
# 4. Carbon footprint: which ingredients matter most?
# ---------------------------------------------------------------
carbon <- purchases %>%
  group_by(ingredient_bought) %>%
  summarise(
    total_kg  = sum(amount_kg),
    total_co2 = sum(carbon_footprint_kg_co2e),
    .groups = "drop"
  ) %>%
  mutate(share_of_co2 = total_co2 / sum(total_co2),
         share_of_kg  = total_kg / sum(total_kg)) %>%
  arrange(desc(total_co2))
cat("\n=== Carbon footprint by ingredient ===\n")
print(carbon)

p7 <- ggplot(carbon, aes(reorder(ingredient_bought, total_co2), total_co2)) +
  geom_col(fill = "#0F6E56") +
  coord_flip() +
  labs(title = "Total carbon footprint by ingredient", x = NULL, y = "kg CO2e")
save_plot(p7, "carbon_by_ingredient")

# ---------------------------------------------------------------
# 5. Rule of thumb for keeping a factor
#    Keep it if eta squared >= 0.05 OR tree importance >= 10%.
# ---------------------------------------------------------------
cat("\n=== Factors to keep ===\n")
cat("Tree 1:", paste(att_effect$factor[att_effect$eta_sq >= 0.05], collapse = ", "), "\n")
cat("Tree 2:", paste(dish_effect$factor[dish_effect$eta_sq >= 0.05], collapse = ", "), "\n")
cat("Also keep any numeric predictor with importance >= 10% in the rpart output above.\n")

# Put every graph in one PDF so they can be viewed together.
all_plots_pdf <- file.path("plots", "all_factor_graphs.pdf")
pdf(all_plots_pdf, width = 11, height = 7.5, onefile = TRUE)
print(p1)
print(p2)
print(p3)
print(p4)
rpart.plot(tree1, main = "Tree 1: predicted turnout", type = 4, extra = 101)
print(p5)
print(p6)
print(p6_period)
rpart.plot(tree2, main = "Tree 2: share of dish left over", type = 4, extra = 101)
print(p7)
print(p8)
dev.off()

cat("\nAll graphs saved in:", normalizePath(all_plots_pdf), "\n")
if (.Platform$OS.type == "windows") {
  shell.exec(normalizePath(all_plots_pdf))
} else {
  browseURL(normalizePath(all_plots_pdf))
}
