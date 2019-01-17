import { Version } from '@microsoft/sp-core-library';
import {
  BaseClientSideWebPart,
  IPropertyPaneConfiguration,
  PropertyPaneTextField,
  PropertyPaneCheckbox,
  PropertyPaneLabel,
  PropertyPaneLink,
  PropertyPaneSlider,
  PropertyPaneToggle,
  PropertyPaneDropdown
} from '@microsoft/sp-webpart-base';
import { escape } from '@microsoft/sp-lodash-subset';

import styles from './HelloWorldWebPart.module.scss';
import * as strings from 'HelloWorldWebPartStrings';

export interface IHelloWorldWebPartProps {
  description: string;
  task: boolean;
  propertyToggle: boolean;
}

export default class HelloWorldWebPart extends BaseClientSideWebPart<IHelloWorldWebPartProps> {

  public render(): void {
    this.domElement.innerHTML = `
      <div class="${ styles.helloWorld }">
        <div class="${ styles.container }">
          <div class="${ styles.row }">
            <div class="${ styles.column }">
              <span class="${ styles.title }">Welcome to SharePoint!</span>
              <p class="${ styles.subTitle }">Customize SharePoint experiences using Web Parts.</p>
              <p class="${ styles.description }">${escape(this.properties.description)}</p>
              <a href="https://aka.ms/spfx" class="${ styles.button }">
                <span class="${ styles.label }">Learn more</span>
              </a>
            </div>
          </div>
        </div>
      </div>`;
  }

  protected get dataVersion(): Version {
    return Version.parse('1.0');
  }

  protected get disableReactivePropertyChanges(): boolean { 
    return false; /* Modo No reactivo desactivado */
  }

  protected getPropertyPaneConfiguration(): IPropertyPaneConfiguration {
    
    let templateProperty: any;
    if (this.properties.propertyToggle) {
      templateProperty = PropertyPaneTextField('propertyOn', {
        label: 'Propiedades cuando el switch está activado.'
      });
    } else {
      templateProperty = PropertyPaneDropdown('propertyOff', {
        label: 'Propiedades cuando el switch está desactivado.',
        options: [{key: "Opcion1", text: "Opción 1"}, {key: "Opcion2", text: "Opción 2"}]
      });
    }
    
    return {
      pages: [
        {
          header: {
            description: strings.PropertyPaneDescription
          },
          groups: [
            {
              groupName: strings.BasicGroupName,
              groupFields: [
                PropertyPaneTextField('description', {
                  label: strings.DescriptionFieldLabel  }),
                PropertyPaneCheckbox('task', {
                  text: "Tareas", checked: true }),
                PropertyPaneSlider('numtasks', {
                  label: "Número máximo de tareas.",  value: 0, max: 100, min: 0, showValue: true }),
                  PropertyPaneToggle('propertyToggle', {
                    label: 'Switch'
                  }),
                  templateProperty
              ]
            }
          ]
        }
      ]
    };
  }
}
