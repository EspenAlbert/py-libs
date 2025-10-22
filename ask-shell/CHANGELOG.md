# Changelog

## 0.2.1 2025-10-22T06-49Z

### Console
- fix: Adds flag for skip_rich_exception instead of hard-coded [123bf4](https://github.com/EspenAlbert/py-libs/commit/123bf4)


## 0.2.0 2025-10-19T17-16Z

### __Root__
- New class AskShellSettings

### Ask
- New function confirm
- New function text
- New function select_list_multiple
- New function select_list_multiple_choices
- New function select_dict
- New function select_list
- New function select_list_choice
- New class NewHandlerChoice
- New class ChoiceTyped
- New class SelectOptions
- New class KeyInput
- New class PromptMatch
- New class question_patcher
- New class force_interactive
- New class raise_on_question
- New exception RaiseOnQuestionError

### Console
- New function configure_logging
- New function add_renderable
- New function get_live_console
- New function print_to_live
- New function log_to_live
- New class RemoveLivePart
- New function interactive_shell
- New class new_task

### Shell
- New function kill
- New function kill_all_runs
- New function stop_runs_and_pool
- New function run
- New function run_and_wait
- New function run_error
- New function wait_on_ok_errors
- New class ShellRun
- New class run_pool
- New class ShellConfig
- New class handle_interrupt_wait
- New exception ShellError

### Shell_Events
- New class ShellRunStdStarted
- New class ShellRunStdOutput
- New class ShellRunPOpenStarted
- New class ShellRunStdReadError
- New class ShellRunRetryAttempt
- New class ShellRunBefore
- New class ShellRunAfter
- New type_alias OutputCallbackT
- New type_alias ShellRunCallbackT
