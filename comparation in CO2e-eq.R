library(ggplot2)
library(tidyr)

#Pre-service preparation - Software, Post-service Leftover - Software + Donation
#Unit:CO2e/kg

#Baseline waste categories & weight
waste_df <- data.frame(
    category = c('Pre-service Preparation', 'Post-service Leftover', 'Student-plate Leftover'),
    mass_baseline = c(18000, 24500, 21250)
)
waste_df$category <- factor(waste_df$category, levels = c('Pre-service Preparation', 'Post-service Leftover', 'Student-plate Leftover'))

red_pre <- 0.25 #Software reduces about 25% pre-service Preparation
don_buffet_rate <- 0.6 #60% of the post-service leftover can be donated

#Pre-service waste after using built-in OS
m_pre_soft <- waste_df$mass_baseline[1] * (1-red_pre) #Mass of waste after software
mass_red <- waste_df$mass_baseline[1] - m_pre_soft #Mass of reduction

#Post-service waste after donation
m_post_soft <- waste_df$mass_baseline[2] * (1-red_pre) #Mass of waste after software
m_post_don <- m_post_soft * don_buffet_rate #Mass of waste for donation
m_post <- m_post_soft - m_post_don #Mass of Waste left in dining hall

#Student-plate leftover - no change without considering point system
m_plate <- waste_df$mass_baseline[3]

#Add new weight to waste_df
waste_df$mass_int <- waste_df$mass_baseline
waste_df$mass_int[waste_df$category== 'Pre-service Preparation'] <- m_pre_soft
waste_df$mass_int[waste_df$category== 'Post-service Leftover'] <- m_post
waste_df$mass_int[waste_df$category== 'Student-plate Leftover'] <- m_plate

#tonne CO2e-eq / kg
avg_EF <- 2.8 #By weighted avg of the datasets of ingredients - 280kg
waste_df$co2e_baseline <- waste_df$mass_baseline * avg_EF / 1000
waste_df$co2e_intervention <- waste_df$mass_int * avg_EF / 1000

#Organize data
plot_data <- pivot_longer(
  waste_df,
  cols = c(co2e_baseline, co2e_intervention),
  names_to = 'scenario',
  values_to = 'co2_tonne'
)
plot_data$scenario <- ifelse(
  plot_data$scenario == 'co2e_baseline', 'Baseline', 'Software + Donation Intervention'
)

#Plot
ggplot(plot_data, aes(x = scenario, y = co2_tonne, fill = category)) +
  geom_col(position = position_dodge(width = 0.8), width = 0.7) +
  labs(x = 'Scenario', y = expression(Carbon~footprint~of~food~waste~(tonnes~CO[2]-eq)),
       fill = 'Food-waste category'
  ) +
  theme_bw()
